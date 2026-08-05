"""Thinking-mode AV: a fresh, self-contained AV loader/injector for the
thinking-mode project — deliberately NOT sharing code with the affine-map
(W/b) project (experiments/affine_map.py, train_affine.py, local_av.py).
That project's code and results stay untouched and independently showable;
this is a new, separate line of experiments on the same released checkpoint.

Only genuinely general, pre-existing upstream-adjacent utilities are reused
(nla_inference.py's NLAConfig/load_nla_config/normalize_activation/
inject_at_marked_positions/resolve_embed_scale, nla.schema's NLACritic) —
these predate the affine-map project and are shared infrastructure the
original baseline_fve.py (SGLang) already depended on, not something
introduced for it.

The idea: give the AV a private "thinking" scratchpad before its official
explanation. Two design decisions, both argued through at length in
conversation before writing this file — recorded here so the reasoning
travels with the code, not just in RESEARCH_LOG.md:

  - AR NEVER sees the thinking section, only the extracted <explanation>.
    Letting AR score thinking too would hand the model a second, LESS
    scrutinized channel to stash reconstruction-useful-but-meaningless
    content in — worse than the existing filler problem, not better, since
    a "private scratchpad" is expected to be messy and gets even less
    human scrutiny than the official explanation already does.
  - The opening <thinking> tag is SEEDED directly into the prompt (assistant
    turn pre-filled with "<thinking>\n"), not left for the model to invent.
    There is no SFT anywhere in this project (Tier 1/2 only) — the model has
    to discover the two-tag structure through RL alone, which is a real,
    additional cold-start burden on top of whatever RL is already trying to
    teach. Seeding the opening tag removes "invent the tag vocabulary from
    nothing" from that burden; the model only has to learn when to close it.

`use_thinking=False` reproduces the ORIGINAL, unmodified prompt/behavior
exactly (no addition, no seeding) — kept as a toggle on the SAME class so
Tier 1's "does this help at all" comparison is a true paired comparison, one
model, one file, not two separately-implemented paths that could subtly
drift apart.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from nla_inference import (  # noqa: E402
    NLAConfig,
    inject_at_marked_positions,
    load_nla_config,
    normalize_activation,
    resolve_embed_scale,
)

# Same regex shape as nla.schema.extract_explanation — defined fresh here
# rather than imported, so this module has zero dependency on any file
# touched by the affine-map project, however indirect.
_THINKING_RE = re.compile(r"<thinking>\s*(.*?)\s*</thinking>", re.DOTALL)
_EXPLANATION_RE = re.compile(r"<explanation>\s*(.*?)\s*</explanation>", re.DOTALL)

# A fully STANDALONE prompt, replacing the earlier append-onto-original
# design. This is NOT built from self.cfg.actor_prompt_template in any way —
# no concatenation, no substring of it. self.cfg.actor_prompt_template is
# loaded fresh from the checkpoint's own nla_meta.yaml sidecar on every
# ThinkingAV.__init__ call and is never read, mutated, or referenced by this
# constant; use_thinking=False still uses that original template exactly as
# released. The two prompts are architecturally independent objects living in
# two different places (sidecar YAML vs. this Python constant) — see
# ThinkingAV.__init__ and _content_for below, where the choice between them is
# a plain if/else, not a derivation.
#
# Rewritten (from the original append-only addition) after research into
# metacognitive prompting (5 stages: comprehend -> preliminary interpretation
# -> critically evaluate -> finalize decision -> assess confidence) and
# Plan-and-Solve prompting, plus Anthropic's own prompt-engineering guidance
# on tag-paired sections. All 5 metacognitive stages happen INSIDE <thinking>,
# in their original order (a", "b", "c", "d", "e" below) — an earlier draft
# split stage 4 (finalize) into <thinking> and stage 5 (assess confidence)
# into <explanation> that was incoherent, since confidence-assessment must
# come AFTER the decision it's assessing, not before it. <explanation> is
# therefore a clean write-up step only, not a second decision point. Full
# evolution of this design recorded in RESEARCH_LOG.md section 9.
_THINKING_PROMPT_TEMPLATE = (
    "You are a meticulous AI researcher conducting an important investigation into activation vectors from a language model.\n\n"
    "We will pass the vector enclosed in <concept> tags into your context.\n\n"
    "Here is the vector:\n\n"
    "<concept>{injection_char}</concept>\n\n"
    "Your task has two steps, always in this exact order:\n\n"
    "1. First, inside <thinking> tags, work through the vector as follows:\n"
    "   a. Briefly restate what you are trying to do: interpret what this activation vector might represent.\n"
    "   b. Form an initial guess about its content.\n"
    "   c. Question that guess — consider what might be wrong with it, and what else it could be.\n"
    "   d. Settle on your actual conclusion.\n"
    "   e. Note how confident you are in that conclusion, and why.\n"
    "   Keep this to about 10 sentences total. Close this section with </thinking> when you are done.\n\n"
    "2. Then, in a new, separate section, produce an explanation for the vector, enclosed within <explanation> tags. The explanation consists of 2-3 text snippets describing that vector. Close this section with </explanation> when you are done.\n\n"
    "Do not put your explanation inside the <thinking> tags, and do not put your thinking inside the <explanation> tags — the two sections are separate, and each must be fully opened and closed with its own tags.\n\n"
    "Follow this exact format:\n"
    "<thinking>\n"
    "[your reasoning, following steps a-e above]\n"
    "</thinking>\n"
    "<explanation>\n"
    "[your explanation]\n"
    "</explanation>"
)

# --- v4 prompt: matched to the v4 training data's register -----------------
#
# Why this exists. The template above asks for a five-step labelled structure
# (a: restate, b: initial guess, c: question it, d: conclude, e: confidence).
# The v4 SFT targets are nothing like that — they are loose first-person
# hedged prose written by the base model. Training against the a-e prompt
# while the target is v4 prose means SFT spends its capacity fighting the
# prompt in its own context, and makes any result hard to attribute.
#
# Evidence this matters: an aborted v4 SFT run under the a-e prompt had
# schema_collapsed still at 24/50 by the step-0 eval, where the v2 run (whose
# data DID match the a-e structure) reached 1/50 at the same point.
#
# It also explains the rigid "Initial guess: ... Question: ... Final
# conclusion: ... Confidence: moderate" template that the v2 data was
# repeatedly criticised for. That template IS steps a-e. The prompt was
# manufacturing the very structure later effort went into prompting away.
#
# The two-section tag contract is IDENTICAL to the template above (thinking
# then explanation, each opened and closed), so generation staging, the
# stopping criterion, extraction regexes and the seed text are all unchanged.
# Only what section 1 asks for differs.
_THINKING_PROMPT_TEMPLATE_V4 = (
    "You are a meticulous AI researcher conducting an important investigation into activation vectors from a language model.\n\n"
    "We will pass the vector enclosed in <concept> tags into your context.\n\n"
    "Here is the vector:\n\n"
    "<concept>{injection_char}</concept>\n\n"
    "Your task has two steps, always in this exact order:\n\n"
    "1. First, inside <thinking> tags, work out what you can actually tell about this vector, "
    "for a person who wants to understand what was being represented. Write plainly, in your own words:\n"
    "   - What you can tell with reasonable confidence.\n"
    "   - What you genuinely cannot distinguish. If two or three different kinds of content would "
    "look the same to you here, name them.\n"
    "   - Which part you feel least sure about.\n"
    "   How to write it:\n"
    "   - First person, thinking out loud. \"I'd say...\", \"I can't tell whether...\", "
    "\"My guess is...\", \"It might just as easily be...\"\n"
    "   - Short, plain sentences. No stacked clauses.\n"
    "   - Stay at the level of WHAT KIND of thing this is. Do not name a specific brand, product, "
    "place, person, or organization.\n"
    "   - Do not write about the final token or what comes next — that belongs in the explanation.\n"
    "   Close this section with </thinking> when you are done.\n\n"
    "2. Then, in a new, separate section, produce an explanation for the vector, enclosed within <explanation> tags. The explanation consists of 2-3 text snippets describing that vector. Close this section with </explanation> when you are done.\n\n"
    "Do not put your explanation inside the <thinking> tags, and do not put your thinking inside the <explanation> tags — the two sections are separate, and each must be fully opened and closed with its own tags.\n\n"
    "Follow this exact format:\n"
    "<thinking>\n"
    "[what you can tell, following the guidance above]\n"
    "</thinking>\n"
    "<explanation>\n"
    "[your explanation]\n"
    "</explanation>"
)

# Selectable by name so SFT and RL provably share one definition rather than
# each carrying a private copy that can drift.
THINKING_PROMPT_STYLES = {
    "metacognitive": _THINKING_PROMPT_TEMPLATE,   # original a-e structure
    "v4": _THINKING_PROMPT_TEMPLATE_V4,           # matched to v4 SFT targets
}

# What gets appended to the tokenized prompt to seed the opening tag —
# includes a newline so the model's first generated token starts a fresh line,
# matching the format shown in the prompt template.
_SEED_TEXT = "<thinking>\n"


class _ThinkingCloseCriteria(StoppingCriteria):
    """Halts stage-1 (thinking) generation the instant '</thinking>' appears
    in the tokens generated so far, so stage 2 (explanation) can start with a
    fresh, full token budget instead of sharing one pool where a long
    thinking phase crowds out the explanation before its closing tag.

    Only valid for batch_size=1: different samples in a GRPO group close
    thinking at different token positions, so one shared criterion can't give
    each sample in a batch an independent boundary. This is exactly why
    tier2_train_lora.py's sample_group calls generate() once per sample
    (a Python loop) rather than batching via num_return_sequences.

    With inputs_embeds-based generation, the input_ids HF tracks internally
    start empty and grow with ONLY the newly generated tokens (the prompt is
    never echoed back) — the same fact this file already relies on for
    `continuation = tokenizer.batch_decode(gen, ...)` below. So decoding the
    full input_ids handed to __call__ is exactly "everything generated so
    far in this stage," no prompt-length offset needed.
    """

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def __call__(self, input_ids: torch.Tensor, scores: torch.Tensor, **kwargs) -> bool:
        text = self.tokenizer.decode(input_ids[0], skip_special_tokens=True)
        return "</thinking>" in text


class ThinkingAV:
    """Loads the released AV checkpoint locally, with an opt-in thinking-mode
    prompt addition + tag-seeding. `use_thinking=False` on any method call
    reproduces the exact original (unmodified) behavior for paired comparison.

    All AV parameters are frozen — this class never trains the base AV
    weights directly; Tier 2 wraps `.model` in a PEFT LoRA adapter externally
    (see tier2_train_lora.py) rather than this class doing so itself, so this
    loader stays usable standalone for Tier 1 (no LoRA at all).
    """

    def __init__(self, checkpoint_dir: str, device: str = "cuda", dtype: torch.dtype = torch.bfloat16,
                 prompt_style: str = "metacognitive"):
        self.device = device
        self.dtype = dtype
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint_dir, trust_remote_code=True)
        self.cfg: NLAConfig = load_nla_config(checkpoint_dir, self.tokenizer)
        self.model = AutoModelForCausalLM.from_pretrained(
            checkpoint_dir, dtype=dtype, trust_remote_code=True,
        ).to(device)
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad_(False)
        self.embed_scale = resolve_embed_scale(checkpoint_dir)
        self.n_params = sum(p.numel() for p in self.model.parameters())

        # A separate, standalone constant (see _THINKING_PROMPT_TEMPLATE
        # above) — NOT derived from self.cfg.actor_prompt_template, which
        # stays untouched and is still what use_thinking=False uses via
        # _content_for below.
        assert prompt_style in THINKING_PROMPT_STYLES, (
            f"unknown prompt_style {prompt_style!r}; expected one of "
            f"{sorted(THINKING_PROMPT_STYLES)}"
        )
        self.prompt_style = prompt_style
        self.thinking_prompt_template = THINKING_PROMPT_STYLES[prompt_style]

    def _content_for(self, use_thinking: bool) -> str:
        template = self.thinking_prompt_template if use_thinking else self.cfg.actor_prompt_template
        return template.format(injection_char=self.cfg.injection_char)

    def build_injected_embeds(
        self, v_raw: torch.Tensor, *, use_thinking: bool = True,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, int]:
        """Tokenize the (thinking-mode or original) prompt, inject v_raw,
        optionally append the seeded "<thinking>\\n" tokens' embeddings.

        Returns (injected_embeds [1,T,d], ids_t [1,T], v_scaled [d], prompt_len).
        prompt_len is embeds.shape[1] AFTER any seed text is appended (i.e.
        the full length of what's returned as `injected_embeds`/`ids_t`) —
        the boundary a caller needs when concatenating further text embeds
        onto this tensor for teacher-forced log-prob slicing (mirrors the
        same prompt_len bookkeeping train_affine.py's
        compute_group_log_probs uses, reimplemented fresh here).
        """
        content = self._content_for(use_thinking)
        input_ids = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": content}], tokenize=True, add_generation_prompt=True,
        )
        ids_t = torch.tensor(input_ids, dtype=torch.long, device=self.device).unsqueeze(0)

        with torch.no_grad():
            # NO `* self.embed_scale` here. get_input_embeddings() returns the
            # embedding MODULE; calling it runs forward(), and for Gemma that is
            # Gemma3TextScaledWordEmbedding.forward(), which ALREADY multiplies by
            # sqrt(hidden_size). Measured: raw weight-row norm 0.9722 -> forward()
            # output 60.2801, ratio 62.0048 == sqrt(3840). Multiplying again made
            # every token embedding 62x too large and the model emitted repetition
            # loops ("We are looking for\n\nWe are looking for...") even with no
            # vector injected at all.
            #
            # The upstream recipe's "embeds = embeds * embed_scale" applies when you
            # read the raw WEIGHT MATRIX (embed_tokens.weight[ids]) — not when you
            # call the module. This was invisible on Qwen, whose embed_scale is 1.0,
            # so the same wrong line was a silent no-op there.
            #
            # embed_scale is still needed: injected vectors go in at
            # cfg.injection_scale, which is calibrated against ALREADY-SCALED
            # embeddings (Gemma 80000 vs mean scaled-token norm ~60).
            embeds = self.model.get_input_embeddings()(ids_t).to(self.dtype)

        v_scaled = normalize_activation(v_raw.to(device=self.device, dtype=torch.float32), self.cfg.injection_scale)
        v_scaled = v_scaled.to(self.dtype)

        injected = inject_at_marked_positions(
            ids_t, embeds, v_scaled.view(1, -1),
            self.cfg.injection_token_id, self.cfg.injection_left_neighbor_id, self.cfg.injection_right_neighbor_id,
        )

        if use_thinking:
            seed_ids = self.tokenizer(_SEED_TEXT, add_special_tokens=False, return_tensors="pt")["input_ids"].to(self.device)
            with torch.no_grad():
                seed_embeds = self.model.get_input_embeddings()(seed_ids).to(self.dtype)  # no *embed_scale: forward() already scales (see build_injected_embeds)
            injected = torch.cat([injected, seed_embeds], dim=1)
            ids_t = torch.cat([ids_t, seed_ids], dim=1)

        # prompt_len = everything already baked into `injected`/`ids_t` as
        # returned (prompt + seed, if any) — this is the boundary a caller
        # needs when concatenating further text embeds onto THIS tensor
        # (see compute_teacher_forced_log_probs). Computed AFTER the seed is
        # appended, not before — getting this backwards would misalign the
        # log-prob slice by exactly the seed's length, silently.
        prompt_len = injected.shape[1]

        return injected, ids_t, v_scaled, prompt_len

    @torch.no_grad()
    def generate(
        self, v_raw: torch.Tensor, *, use_thinking: bool = True,
        thinking_max_tokens: int = 400, explanation_max_tokens: int = 200,
        temperature: float = 1.0, do_sample: bool = True,
    ) -> tuple[str, str | None, str | None, str]:
        """One activation -> (full raw text, thinking or None, explanation or
        None, raw continuation text).

        use_thinking=True runs TWO generation stages against the same prompt:

          Stage 1 (thinking): sample with a StoppingCriteria that halts the
          instant '</thinking>' appears; thinking_max_tokens (default 400) is
          only a safety backstop if it never closes.

          Stage 2 (explanation): a FRESH, FULL explanation_max_tokens budget
          (default 200) starting right after stage 1's own output — matching
          the original released model's explanation budget exactly, rather
          than sharing one pool where a long thinking phase crowds out the
          explanation before its closing tag.

        Staging the SAMPLING this way does not sever the RL training
        connection to the thinking tokens: compute_teacher_forced_log_probs
        always does ONE unified pass over the combined continuation
        afterward, regardless of how many generate() calls produced it.

        use_thinking=False is unchanged: one stage, explanation_max_tokens,
        reproducing the exact original behavior for paired comparison.

        Returns a 4-tuple; the 4th element (raw continuation text — thinking
        + explanation content exactly as generated, no seed prefix) is what
        tier2_train_lora.py's sample_group collects per sample for
        teacher-forced log-prob computation.
        """
        embeds, ids_t, _, prompt_len = self.build_injected_embeds(v_raw, use_thinking=use_thinking)

        if use_thinking:
            stop_criteria = StoppingCriteriaList([_ThinkingCloseCriteria(self.tokenizer)])
            stage1_gen = self.model.generate(
                inputs_embeds=embeds, max_new_tokens=thinking_max_tokens,
                do_sample=do_sample, temperature=temperature,
                stopping_criteria=stop_criteria,
            )
            stage1_embeds = self.model.get_input_embeddings()(stage1_gen).to(self.dtype)  # no *embed_scale: forward() already scales
            stage2_embeds = torch.cat([embeds, stage1_embeds], dim=1)
            stage2_gen = self.model.generate(
                inputs_embeds=stage2_embeds, max_new_tokens=explanation_max_tokens,
                do_sample=do_sample, temperature=temperature,
            )
            # stage2_gen is stage 2's NEW tokens only (same
            # never-echoes-input fact as everywhere else in this file) — the
            # full continuation is both stages concatenated.
            gen = torch.cat([stage1_gen, stage2_gen], dim=1)
        else:
            gen = self.model.generate(
                inputs_embeds=embeds, max_new_tokens=explanation_max_tokens,
                do_sample=do_sample, temperature=temperature,
            )

        # gen contains ONLY the newly generated continuation (inputs_embeds
        # path never echoes input tokens back).
        continuation = self.tokenizer.batch_decode(gen, skip_special_tokens=True)[0]

        # CRITICAL: extraction must run on the continuation alone, never on
        # prompt+continuation together. The sidecar's own instruction text
        # contains the literal substring "<explanation>" ("...enclosed within
        # <explanation> tags...") — searching the full prompt+generation text
        # matches THAT occurrence first and then non-greedily captures
        # everything up to the model's real closing tag, silently corrupting
        # every extracted explanation with a chunk of the prompt's own
        # instructions prepended. Caught on the first live Tier 1 run, not in
        # review — exactly why this got a live smoke test before Tier 2.
        # If use_thinking, the model's own continuation never contains the
        # opening tag (it was seeded into the PROMPT, not generated), so it
        # has to be prepended back here for extraction to find it at all —
        # matches the same pattern already used correctly in
        # tier2_train_lora.py's train_step_for_activation.
        extraction_text = (_SEED_TEXT + continuation) if use_thinking else continuation
        # `text` returned to the caller is the full displayed sequence
        # (prompt/seed + continuation) for printing/debugging ONLY — never
        # feed this into either regex.
        full_ids = torch.cat([ids_t, gen], dim=1)
        text = self.tokenizer.batch_decode(full_ids, skip_special_tokens=True)[0]

        thinking_match = _THINKING_RE.search(extraction_text)
        explanation_match = _EXPLANATION_RE.search(extraction_text)
        thinking = thinking_match.group(1).strip() if thinking_match else None
        explanation = explanation_match.group(1).strip() if explanation_match else None
        return text, thinking, explanation, continuation

    def compute_teacher_forced_log_probs(
        self, v_raw: torch.Tensor, texts: list[str], *, use_thinking: bool = True,
    ) -> torch.Tensor:
        """Grad-enabled teacher-forcing, reimplemented fresh for this module
        (mirrors train_affine.py's compute_group_log_probs mechanically, but
        is its own independent copy — no import from that file, per the
        "keep separate" requirement).

        `texts` must be exactly the model's own GENERATED CONTINUATION for
        each sample (i.e. `tokenizer.batch_decode(gen, ...)` from
        `model.generate()`'s output) — NOT the full displayed text from
        `generate()` above, which also includes the seeded "<thinking>\\n"
        prefix. That prefix is prompt-side and already baked into `embeds`
        via `build_injected_embeds(use_thinking=True)`; re-including it in
        `texts` would double-count it and misalign every log-prob after it,
        the same class of bug just fixed in `prompt_len`'s bookkeeping above.
        This computes log-probs over the whole continuation (thinking +
        explanation content, minus only the seed); the reward function is
        what restricts what gets SCORED to the extracted <explanation> only
        (see tier2_train_lora.py) — this method just needs correct log-probs
        for whatever sequence of tokens was actually sampled, same principle
        as ever since verify_local_grad.py.
        """
        embeds, _, _, prompt_len = self.build_injected_embeds(v_raw, use_thinking=use_thinking)
        log_probs = []
        for text in texts:
            ids = self.tokenizer(text, return_tensors="pt", add_special_tokens=False).input_ids.to(self.device)
            if ids.shape[1] == 0:
                log_probs.append(torch.zeros((), device=self.device))
                continue
            with torch.no_grad():
                text_embeds = self.model.get_input_embeddings()(ids).to(self.dtype)  # no *embed_scale: forward() already scales
            full_embeds = torch.cat([embeds, text_embeds], dim=1)
            logits = self.model(inputs_embeds=full_embeds).logits
            pred_logits = logits[:, prompt_len - 1:-1, :]
            lp = torch.log_softmax(pred_logits.float(), dim=-1)
            token_lp = torch.gather(lp, dim=-1, index=ids.unsqueeze(-1)).squeeze(-1)
            log_probs.append(token_lp.mean())
        return torch.stack(log_probs)

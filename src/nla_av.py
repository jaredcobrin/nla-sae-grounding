"""Run a released NLA verbalizer: activation in, explanation text out.

ATTRIBUTION (Apache-2.0 section 4(b) -- this file is MODIFIED derived work)
    Derived from `NLAClient` in `nla_inference.py` of
    kitft/natural_language_autoencoders, Copyright 2026 Anthropic PBC,
    licensed under the Apache License 2.0. It CALLS that project's
    `inject_at_marked_positions`, `normalize_activation`, `resolve_embed_scale`
    and `load_nla_config` rather than copying them, and follows the same
    injection recipe as `NLAClient._build_embeds`.

    Changed here: the Gemma-3 embed-scale fix described below; a
    single-activation `generate()` in place of the batch and SGLang paths; and a
    locally-defined explanation regex. See NOTICE at the repo root.

Vendored rather than imported because this fork modified it, and because the
injection path is the least forgiving code in the stack.

THE GEMMA EMBED-SCALE TRAP, which is why this file exists at all.
`get_input_embeddings()` returns the embedding MODULE; calling it runs
`Gemma3TextScaledWordEmbedding.forward()`, which ALREADY multiplies by
sqrt(hidden_size). The upstream recipe's `embeds = embeds * embed_scale` applies
when you index the weight matrix directly, NOT when you call the module. Doing
both makes every token embedding 62x too large, and the symptom is not a crash
-- it is repetition loops, present even with no injection. Measured: raw
weight-row norm 0.9722 -> forward() output 60.2801, ratio 62.0048 == sqrt(3840).
Invisible on Qwen, whose embed_scale is 1.0.

embed_scale is still needed for one thing: the injected vector goes in at
cfg.injection_scale, calibrated against ALREADY-SCALED embeddings.

TWO OTHER THINGS THAT BIT US HERE
- Extraction must run on the CONTINUATION ALONE, never prompt+continuation. The
  prompt's own instructions contain the literal substring "<explanation>", so
  searching the full text matches that first and silently prepends a chunk of
  the prompt to every extracted explanation.
- The injection hook scans for the marker token inside the hook rather than
  using a precomputed index, which is wrong by construction once samples are
  reordered.

DEBUGGING: if injection silently fails, the AV describes the literal CJK marker
character and free-associates in Chinese. Grepping output for CJK is the loudest
smoke test for the whole stack, and the pipeline checks for it.

PROVENANCE: this began as the AV wrapper for a separate <thinking>-scratchpad
experiment that lives in the previous repo. Every thinking-mode path has been
removed here and the result verified bit-identical -- same seed, same
explanations, same FVE to 4 decimals.
"""



from __future__ import annotations

import re
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

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
_EXPLANATION_RE = re.compile(r"<explanation>\s*(.*?)\s*</explanation>", re.DOTALL)

# The AV's own prompt comes from the checkpoint's nla_meta.yaml sidecar
# (cfg.actor_prompt_template) and is used unmodified. Nothing here rewrites
# or appends to it.


class AVRunner:
    """Loads the released AV checkpoint and verbalizes activations with it.
    reproduces the exact original (unmodified) behavior for paired comparison.

    All AV parameters are frozen — this class never trains the base AV
    weights directly; Tier 2 wraps `.model` in a PEFT LoRA adapter externally
    (see tier2_train_lora.py) rather than this class doing so itself, so this
    loader stays usable standalone for Tier 1 (no LoRA at all).
    """

    def __init__(self, checkpoint_dir: str, device: str = "cuda", dtype: torch.dtype = torch.bfloat16):
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
        # above) — NOT derived from self.cfg.actor_prompt_template, which
        # _content_for below.

    def _content_for(self) -> str:
        template = self.cfg.actor_prompt_template
        return template.format(injection_char=self.cfg.injection_char)

    def build_injected_embeds(
        self, v_raw: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, int]:
        """Tokenize the AV prompt, inject v_raw,

        Returns (injected_embeds [1,T,d], ids_t [1,T], v_scaled [d], prompt_len).
        prompt_len is embeds.shape[1] AFTER any seed text is appended (i.e.
        the full length of what's returned as `injected_embeds`/`ids_t`) —
        the boundary a caller needs when concatenating further text embeds
        onto this tensor for teacher-forced log-prob slicing (mirrors the
        same prompt_len bookkeeping train_affine.py's
        compute_group_log_probs uses, reimplemented fresh here).
        """
        content = self._content_for()
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
        self, v_raw: torch.Tensor, *, explanation_max_tokens: int = 200,
        temperature: float = 1.0, do_sample: bool = True,
    ) -> str | None:
        """One activation -> the extracted <explanation> text, or None.

        None means extraction failed: the model did not emit a well-formed tag
        pair. Callers must treat that as a failure, not as an empty
        explanation -- scoring it as empty silently rewards a broken
        generation.
        """
        embeds, ids_t, _, prompt_len = self.build_injected_embeds(v_raw)

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
        extraction_text = continuation
        # `text` returned to the caller is the full displayed sequence
        # (prompt/seed + continuation) for printing/debugging ONLY — never
        # feed this into either regex.
        full_ids = torch.cat([ids_t, gen], dim=1)
        text = self.tokenizer.batch_decode(full_ids, skip_special_tokens=True)[0]

        explanation_match = _EXPLANATION_RE.search(extraction_text)
        explanation = explanation_match.group(1).strip() if explanation_match else None
        return explanation


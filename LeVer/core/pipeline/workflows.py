import json
import os

from core.kani_templates import KANI_ELIGIBLE, UNVERIFIED_SURFACE
from core.logger import GLOBAL_LOGGER
from core.pipeline.dataset import build_dataset_targets
from core.pipeline.iteration import run_common_pipeline
from core.pipeline.solidity_utils import is_plausible_solidity_source


THREE_MODES = {"full", "lean_only", "no_lean"}

#: Solana modes that run the Kani stage. "lean_only" is the CLI's lean mode.
SOLANA_KANI_MODES = {"full", "lean_only"}

#: Static default Kani property set until property selection is wired in.
DEFAULT_SOLANA_KANI_PROPERTIES = tuple(
    pid for pid in ("SOL-01", "SOL-02", "SOL-04", "SOL-07", "SOL-08") if pid in KANI_ELIGIBLE
)

_KANI_PROPERTY_STATUS = {"SUCCESSFUL": "passed", "FAILED": "failed"}
_SCAFFOLD_WARNING = (
    "Kani harnesses are unfilled scaffold placeholders (harness generation fell back); "
    "this result proves nothing about the program."
)


def _read_iteration_metrics(ctx):
    path = os.path.join(ctx.workspace, f"metrics_iter_{ctx.iteration}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except (OSError, json.JSONDecodeError):
        return {}, path


def _write_pipeline_result(ctx, *, mode, passed, max_iters, model, reason=""):
    metrics, metrics_path = _read_iteration_metrics(ctx)
    lean_enabled = mode in {"full", "lean_only"}
    non_lean_enabled = mode in {"full", "no_lean"}
    lean_passed = metrics.get("formal_success") is True if lean_enabled else None
    non_lean_passed = None
    if non_lean_enabled:
        # In full, formal verification is non-blocking under the legacy policy,
        # so the overall decision is also the non-Lean decision.
        non_lean_passed = bool(passed)

    slither_enabled = bool(metrics.get("slither_enabled", False))
    audit_enabled = bool(metrics.get("llm_audit_enabled", False))
    external_evaluation_enabled = slither_enabled or audit_enabled
    external_evaluation_complete = external_evaluation_enabled and (
        (
            not slither_enabled
            or (
                not metrics.get("slither_infra_broken", False)
                and metrics.get("slither_pass") is not None
            )
        )
        and (
            not audit_enabled
            or (
                not metrics.get("llm_audit_infra_broken", False)
                and metrics.get("llm_audit_pass") is not None
            )
        )
    )
    result = {
        "mode": mode,
        "model": model,
        "decision_policy": "legacy_core_lenient",
        "passed": bool(passed),
        "iterations": ctx.iteration,
        "max_iterations": max_iters,
        "reason": reason,
        "lean": {
            "enabled": lean_enabled,
            "passed": lean_passed,
        },
        "non_lean": {
            "enabled": non_lean_enabled,
            "passed": non_lean_passed,
        },
        "external_evaluation": {
            "enabled": external_evaluation_enabled,
            "affects_iteration": False,
            "complete": external_evaluation_complete if external_evaluation_enabled else None,
            "slither_pass": metrics.get("slither_pass"),
            "llm_audit_pass": metrics.get("llm_audit_pass"),
        },
        "metrics_path": metrics_path,
    }
    path = os.path.join(ctx.workspace, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return result


def workflow_from_requirement(ctx, agents, tools, requirement, mode, max_iters=3):
    """Run one of the three public requirement-to-verification workflows."""
    if mode not in THREE_MODES:
        raise ValueError(f"Unsupported mode: {mode}")

    simulator = tools["simulator"]
    model = agents["coder"].model_name
    ctx.checkpoint.save_stage("original_requirement", requirement)
    last_reason = "maximum iterations exhausted"

    while ctx.iteration < max_iters:
        ctx.iteration += 1
        print(f"\n======== ITERATION {ctx.iteration}/{max_iters} ({mode}) ========")

        if ctx.iteration == 1:
            print("1. Generating Solidity from requirement...")
            candidate = agents["coder"].generate_modern_code(requirement)
        else:
            print("1. Repairing the current Solidity implementation...")
            constraints = ctx.feedback_constraints + [
                f"Enforce property: {item}" for item in ctx.security_patches
            ]
            repair_prompt = f"""
            [ORIGINAL REQUIREMENT]
            {requirement}

            [CURRENT SOLIDITY]
            {ctx.solidity_code}

            Return a complete repaired Solidity implementation that still satisfies
            the original requirement and addresses every supplied constraint.
            """
            candidate = agents["coder"].generate_code(repair_prompt, constraints)

        if not is_plausible_solidity_source(candidate):
            last_reason = "Solidity generation returned empty or structurally invalid source"
            ctx.feedback_constraints.append(last_reason)
            print(f"   FAILED: {last_reason}")
            continue

        ctx.solidity_code = candidate
        ctx.checkpoint.save_stage("solidity_code", candidate)
        with open(os.path.join(ctx.workspace, "Target.sol"), "w", encoding="utf-8") as f:
            f.write(candidate)

        print("2. Compiling generated Solidity...")
        simulator.initialize_environment(candidate, "")
        compile_ok, compile_log = simulator.check_compilation()
        if not compile_ok:
            last_reason = "Generated Solidity did not compile"
            compiler_feedback = compile_log[-6000:]
            ctx.feedback_constraints.append(
                f"Fix all Solidity compiler errors. Compiler output:\n{compiler_feedback}"
            )
            print(f"   FAILED: {last_reason}")
            continue

        print("3. Running configured verification stages...")
        passed = run_common_pipeline(
            ctx=ctx,
            agents=agents,
            tools=tools,
            skip_proofs=(mode == "no_lean"),
            ablation_mode="full",
            user_targets=[requirement],
            run_llm_audit=(mode != "lean_only"),
            run_slither=(mode != "lean_only"),
            run_non_lean=(mode != "lean_only"),
            require_formal_success=(mode == "lean_only"),
        )
        if passed:
            _write_pipeline_result(
                ctx,
                mode=mode,
                passed=True,
                max_iters=max_iters,
                model=model,
                reason="legacy_core_lenient criteria passed",
            )
            return True

        last_reason = "required verification stages did not pass"
        ctx.checkpoint.clear_stage("definitions_code")

    _write_pipeline_result(
        ctx,
        mode=mode,
        passed=False,
        max_iters=max_iters,
        model=model,
        reason=last_reason,
    )
    return False

def workflow_modern_verification(
    ctx,
    agents,
    tools,
    dataset_item,
    max_iters=8,
    skip_proofs=False,
    ablation_mode="full",
    run_llm_audit=True,
    run_slither=True,
    reuse_target_root=None,
):
    contract_name = dataset_item.get("contract_name", "Unknown_Contract")
    raw_prompt = dataset_item.get("prompt", "")
    user_targets = build_dataset_targets(dataset_item)

    print(f"\nSTARTING CASE: {contract_name}")

    # Initialize the simulation_env layout required by forge build.
    # At this point, create only base files such as foundry.toml, not mocks.
    tools['simulator']._setup_fs()

    while ctx.iteration < max_iters:
        ctx.iteration += 1
        print(f"\n======== ITERATION {ctx.iteration} ========")

        # --- Step 1: Code Generation ---
        if ctx.iteration == 1:
            reused_target_path = None
            if reuse_target_root:
                reused_target_path = os.path.join(
                    reuse_target_root,
                    f"run_{contract_name}",
                    "simulation_env",
                    "src",
                    "Target.sol",
                )
                if not os.path.exists(reused_target_path):
                    reused_target_path = os.path.join(
                        reuse_target_root,
                        f"run_{contract_name}",
                        "Target.sol",
                    )

            if reused_target_path and os.path.exists(reused_target_path):
                print(f"   Reusing frozen Target.sol: {reused_target_path}")
                with open(reused_target_path, "r", encoding="utf-8") as f:
                    ctx.solidity_code = f.read()
                ctx.checkpoint.save_stage("solidity_code", ctx.solidity_code)
                ctx.checkpoint.save_stage("reused_target_path", os.path.abspath(reused_target_path))
            elif ctx.checkpoint.has_stage("solidity_code"):
                print("   Resuming from checkpoint...")
                ctx.solidity_code = ctx.checkpoint.load_stage("solidity_code")
            else:
                ctx.solidity_code = agents['coder'].generate_modern_code(raw_prompt)
                if is_plausible_solidity_source(ctx.solidity_code):
                    ctx.checkpoint.save_stage("solidity_code", ctx.solidity_code)
        else:
            # Repair the candidate after a failed iteration.
            print("Fixing Code based on feedback...")
            constraints = ctx.feedback_constraints + [f"Enforce property: {p}" for p in ctx.security_patches]
            fix_req = f"""
            Refactor the [CURRENT CODE] to fix security issues identified in [CONSTRAINTS].
            [ORIGINAL REQUIREMENTS]
            {raw_prompt}
            [CURRENT CODE]
            {ctx.solidity_code}
            """
            ctx.solidity_code = agents['coder'].generate_code(fix_req, constraints)
            if is_plausible_solidity_source(ctx.solidity_code):
                ctx.checkpoint.save_stage("solidity_code", ctx.solidity_code)

        if not is_plausible_solidity_source(ctx.solidity_code):
            print("   Critical: SolidityCoder returned empty or structurally invalid Solidity. Aborting this case.")
            ctx.checkpoint.clear_stage("solidity_code")
            failure_path = os.path.join(ctx.workspace, "codegen_failure.json")
            with open(failure_path, "w", encoding="utf-8") as f:
                json.dump({
                    "contract_name": contract_name,
                    "iteration": ctx.iteration,
                    "reason": "SolidityCoder returned empty or structurally invalid Solidity",
                }, f, indent=2)
            return False

        # Save Target.sol in the simulation source directory.
        target_save_path = os.path.join(ctx.workspace, "simulation_env", "src", "Target.sol")
        # Keep a backup at the workspace root as well.
        backup_path = os.path.join(ctx.workspace, "Target.sol")

        with open(target_save_path, "w", encoding="utf-8") as f:
            f.write(ctx.solidity_code)
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(ctx.solidity_code)
        print(f"   Target.sol saved to: {target_save_path}")

        # =================================================================================
        # === Step 1.5: compilation guard and automatic repair ===
        # =================================================================================
        print("   Verifying Compilation (Syntax Check)...")
        compilation_success = False
        compilation_retries = 0
        max_comp_retries = 3

        while compilation_retries < max_comp_retries:
            # Run forge build as a syntax and compilation check.
            # Mocks do not exist yet, so a target with external dependencies may fail.
            # The generation prompt requires a single file without local imports.
            success, log = tools['simulator'].check_compilation()

            if success:
                print("      Compilation Passed.")
                compilation_success = True
                break
            else:
                compilation_retries += 1
                print(f"      Compilation Failed (Attempt {compilation_retries}/{max_comp_retries})")
                print(f"      Error Log Summary: {log[:500]}...") # Print only the first 500 characters.

                # Ask the coder to repair compilation errors immediately.
                fix_prompt = f"""
                The Solidity code you generated failed to compile.

                [CODE]
                {ctx.solidity_code}

                [COMPILER ERROR]
                {log}

                [TASK]
                Fix the syntax errors (e.g., Unicode strings, missing semicolons, version mismatch).
                Return the COMPLETE fixed Solidity code.
                """
                # Use the configured fast model for this repair attempt.
                ctx.solidity_code = agents['coder'].generate_code(fix_prompt, ["Fix Compilation Errors"])

                # Save the repaired source again.
                with open(target_save_path, "w", encoding="utf-8") as f:
                    f.write(ctx.solidity_code)
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(ctx.solidity_code)

        if not compilation_success:
            print(f"   Critical: Failed to compile Target.sol after {max_comp_retries} attempts. Aborting this iteration.")
            # Skip later stages after repeated compilation failures and let the
            # outer workflow retry or terminate.
            ctx.feedback_constraints.append("Fix Critical Compilation Errors")
            continue
        # =================================================================================

        # Continue with verification after compilation succeeds.
        is_safe = run_common_pipeline(
            ctx,
            agents,
            tools,
            skip_proofs=skip_proofs,
            ablation_mode=ablation_mode,
            user_targets=user_targets,
            run_llm_audit=run_llm_audit,
            run_slither=run_slither,
        )

        if is_safe:
            print(f"Case {contract_name} passed verification at iteration {ctx.iteration}.")
            return True
        else:
            harness_issue_record = ctx.checkpoint.load_stage("last_harness_issue") or {}
            if harness_issue_record.get("iteration") == ctx.iteration:
                print(
                    f"Case {contract_name} stopped after harness/infrastructure issue at "
                    f"iteration {ctx.iteration}; target repair is intentionally skipped."
                )
                return False
            print(f"Case {contract_name} failed. Retrying...")
            ctx.checkpoint.clear_stage("definitions_code")

    return False

def workflow_full_generation(
    ctx,
    agents,
    tools,
    user_req,
    max_iters,
    skip_proofs,
    ablation_mode="full",
    run_llm_audit=True,
    run_slither=True,
):
    while ctx.iteration < max_iters:
        ctx.iteration += 1
        GLOBAL_LOGGER.log_system("ITERATION_START", f"Iteration {ctx.iteration}")
        print(f"\n======== ITERATION {ctx.iteration} (Mode: Full Gen) ========")

        # Step 1: Code Gen
        if ctx.checkpoint.has_stage("solidity_code") and ctx.iteration == 1:
            print("   Resuming: Loaded Initial Code.")
            ctx.solidity_code = ctx.checkpoint.load_stage("solidity_code")
        else:
            print("Generating Solidity Code...")
            # Supply accumulated security patches as coder constraints.
            constraints = ctx.feedback_constraints + [f"Enforce property: {p}" for p in ctx.security_patches]
            ctx.solidity_code = agents['coder'].generate_code(user_req, constraints)
            ctx.checkpoint.save_stage("solidity_code", ctx.solidity_code)

        # Save the target in the source directory.
        tools['simulator'].save_file("src/Target.sol", ctx.solidity_code)

        if not run_common_pipeline(
            ctx,
            agents,
            tools,
            skip_proofs=skip_proofs,
            ablation_mode=ablation_mode,
            user_targets=[user_req],
            run_llm_audit=run_llm_audit,
            run_slither=run_slither,
        ):
            print("   Triggering Regeneration...")
            ctx.checkpoint.clear_stage("solidity_code")
        else:
            return True

    return False

def workflow_check_and_fix(
    ctx,
    agents,
    tools,
    initial_code,
    max_iters,
    skip_proofs,
    ablation_mode="full",
    run_llm_audit=True,
    run_slither=True,
):
    # Use the injected initial code when the first iteration has no checkpoint.
    if ctx.iteration == 0 and not ctx.checkpoint.has_stage("solidity_code"):
        ctx.solidity_code = initial_code
        ctx.checkpoint.save_stage("solidity_code", ctx.solidity_code)
    elif ctx.checkpoint.has_stage("solidity_code"):
        ctx.solidity_code = ctx.checkpoint.load_stage("solidity_code")

    while ctx.iteration < max_iters:
        ctx.iteration += 1
        print(f"\n======== ITERATION {ctx.iteration} (Mode: Check & Fix) ========")

        # Regenerate the code after a failed prior iteration.
        if ctx.iteration > 1:
            print("Regenerating Fixed Code...")
            # Repair the initial code using accumulated constraints.
            req = f"Refactor and fix the following contract. Improve security based on constraints.\n\n[ORIGINAL CODE]\n{initial_code}"
            constraints = ctx.feedback_constraints + [f"Fix vulnerability: {p}" for p in ctx.security_patches]
            ctx.solidity_code = agents['coder'].generate_code(req, constraints)
            ctx.checkpoint.save_stage("solidity_code", ctx.solidity_code)

        tools['simulator'].save_file("src/Target.sol", ctx.solidity_code)
        with open(os.path.join(ctx.workspace, "Target.sol"), "w", encoding="utf-8") as f:
            f.write(ctx.solidity_code)

        if not run_common_pipeline(
            ctx,
            agents,
            tools,
            skip_proofs=skip_proofs,
            ablation_mode=ablation_mode,
            user_targets=[initial_code],
            run_llm_audit=run_llm_audit,
            run_slither=run_slither,
        ):
            print("   Vulnerability found. Fixing in next iteration...")
            ctx.checkpoint.clear_stage("solidity_code")
        else:
            return True

    return False

def workflow_audit_only(ctx, agents, tools, target_code, skip_proofs, ablation_mode="full", run_llm_audit=True, run_slither=True):
    ctx.iteration = 1
    print("\n======== AUDIT RUN (Mode: Audit Only) ========")

    ctx.solidity_code = target_code
    tools['simulator'].save_file("src/Target.sol", target_code)

    success = run_common_pipeline(
        ctx,
        agents,
        tools,
        audit_mode=True,
        skip_proofs=skip_proofs,
        ablation_mode=ablation_mode,
        user_targets=[target_code],
        run_llm_audit=run_llm_audit,
        run_slither=run_slither,
    )

    if success:
        print("\nAudit result: configured criteria passed.")
    else:
        print("\nAudit result: configured criteria failed.")
    return success

def _kani_skipped(reason):
    return {
        "status": "skipped",
        "reason": reason,
        "fidelity": None,
        "properties": {},
        "messages": [],
        "unverified_surface": list(UNVERIFIED_SURFACE),
    }


def _run_solana_kani(ctx, adapter, code, mode, properties=DEFAULT_SOLANA_KANI_PROPERTIES):
    """Kani stage for the Solana workflow; returns the result.json ``kani`` section.

    Never raises: an exception from spec generation or ``verify_spec`` is recorded as
    ``infra_error``. Only genuine verification failures (non-scaffold fidelity) add
    ``ctx.feedback_constraints``.
    """
    if mode not in SOLANA_KANI_MODES:
        return _kani_skipped(f"kani not run in mode '{mode}'")

    properties = [pid for pid in properties if pid in KANI_ELIGIBLE]
    try:
        spec = adapter.generate_formal_spec(code, properties)
    except Exception as exc:  # LLM / harness-writer failure is tooling, not code
        message = f"infra_error: formal spec generation raised {type(exc).__name__}: {exc}"
        GLOBAL_LOGGER.log_system("KANI_INFRA_ERROR", message)
        print(f"   Kani INFRA ERROR: {message}")
        return {
            "status": "infra_error",
            "fidelity": getattr(adapter, "last_fidelity", None),
            "properties": {pid: "undetermined" for pid in properties},
            "messages": [message],
            "unverified_surface": list(UNVERIFIED_SURFACE),
        }

    if not spec:
        GLOBAL_LOGGER.log_system("KANI_SKIPPED", "no eligible properties")
        print("   Kani skipped: no eligible properties")
        return _kani_skipped("no eligible properties")

    adapter.last_kani_result = None
    try:
        ok, messages = adapter.verify_spec(spec, ctx.workspace)
        messages = list(messages or [])
    except Exception as exc:
        ok = False
        messages = [f"infra_error: verify_spec raised {type(exc).__name__}: {exc}"]
        kani_result = {"infra_error": True}
    else:
        kani_result = getattr(adapter, "last_kani_result", None) or {}

    fidelity = kani_result.get("fidelity") or getattr(adapter, "last_fidelity", None)
    if kani_result.get("infra_error"):
        status = "infra_error"
    else:
        status = "passed" if ok else "failed"

    raw_props = kani_result.get("properties") or {}
    prop_status = {}
    for pid in properties:
        raw = (raw_props.get(pid) or {}).get("status")
        prop_status[pid] = _KANI_PROPERTY_STATUS.get(raw, "undetermined")

    section = {
        "status": status,
        "fidelity": fidelity,
        "properties": prop_status,
        "messages": messages,
        "unverified_surface": list(UNVERIFIED_SURFACE),
    }
    if fidelity == "scaffold":
        section["warning"] = _SCAFFOLD_WARNING
        GLOBAL_LOGGER.log_system("KANI_SCAFFOLD", _SCAFFOLD_WARNING)
        print(f"   WARNING: {_SCAFFOLD_WARNING}")

    # Scaffold harnesses are unfilled placeholders that always fail; their messages
    # say nothing about the program, so they must not steer repair.
    if status == "failed" and fidelity != "scaffold":
        ctx.feedback_constraints.extend(f"Kani: {m}" for m in messages)
    GLOBAL_LOGGER.log_system(
        "KANI_RESULT", json.dumps({"status": status, "fidelity": fidelity, "messages": messages})
    )
    print(f"   Kani {status.upper()} (fidelity: {fidelity})")
    for m in messages:
        print(f"      {m}")
    return section


def workflow_solana_generate_only(ctx, adapter, requirement, mode, max_iters=3):
    """Solana workflow: generate + structurally validate an Anchor program, then Kani.

    Routed through ``SolanaAdapter`` (see core/adapter_factory.py). In modes
    "full"/"lean_only" the Kani stage runs after structural validation and is
    non-blocking: its outcome is recorded in result.json["verification"]["kani"]
    but does not change ``passed``. ``anchor build`` and ``anchor test`` are still
    not executed (SOLANA_VERIFICATION_ROADMAP.md).
    """
    if mode not in THREE_MODES:
        raise ValueError(f"Unsupported mode: {mode}")

    model = getattr(adapter, "model_name", None) or os.getenv("LLM_MODEL", "")
    ctx.checkpoint.save_stage("original_requirement", requirement)
    ctx.checkpoint.save_stage("target", "solana")
    last_reason = "maximum iterations exhausted"
    current_code = ctx.checkpoint.load_stage("anchor_code") or ""

    def _write_result(passed, reason, kani=None):
        result = {
            "target": "solana",
            "mode": mode,
            "model": model,
            "decision_policy": "generation_only",
            "passed": bool(passed),
            "generation_valid": bool(passed),
            "iterations": ctx.iteration,
            "max_iterations": max_iters,
            "reason": reason,
            "verification": {
                "anchor_build": "not_implemented",
                "kani": kani or _kani_skipped("kani stage not reached"),
                "anchor_test": "not_implemented",
            },
        }
        with open(os.path.join(ctx.workspace, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return result

    while ctx.iteration < max_iters:
        ctx.iteration += 1
        print(f"\n======== ITERATION {ctx.iteration}/{max_iters} (solana:{mode}) ========")

        if ctx.iteration == 1 or not current_code:
            print("1. Generating Anchor program from requirement...")
            candidate = adapter.generate_code(
                requirement, [], feedback_constraints=ctx.feedback_constraints or None
            )
        else:
            print("1. Repairing the current Anchor program...")
            candidate = adapter.repair_code(current_code, "\n".join(ctx.feedback_constraints))

        print("2. Validating Anchor program structure...")
        if not adapter.is_valid_source(candidate):
            last_reason = "Anchor generation returned empty or structurally invalid source"
            ctx.feedback_constraints.append(
                "Return ONE complete Anchor program: `use anchor_lang::prelude::*;`, "
                "`declare_id!`, a `#[program]` module and `#[derive(Accounts)]` structs."
            )
            print(f"   FAILED: {last_reason}")
            continue

        current_code = candidate
        ctx.checkpoint.save_stage("anchor_code", candidate)
        with open(os.path.join(ctx.workspace, "Target.rs"), "w", encoding="utf-8") as f:
            f.write(candidate)
        print("   Anchor source saved to Target.rs")

        print(f"3. Kani verification (mode: {mode})...")
        kani = _run_solana_kani(ctx, adapter, candidate, mode)
        ctx.checkpoint.save_stage("kani_result", kani)

        print("4. Anchor build / anchor test: not implemented (see SOLANA_VERIFICATION_ROADMAP.md).")
        _write_result(
            True,
            f"Anchor source generated and structurally validated; Kani {kani['status']}; "
            "build and anchor test stages pending",
            kani=kani,
        )
        return True

    _write_result(False, last_reason, kani=_kani_skipped(
        "kani not run in mode '%s'" % mode if mode not in SOLANA_KANI_MODES
        else "no structurally valid source"
    ))
    return False

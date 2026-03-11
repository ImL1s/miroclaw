/**
 * @mirofish/core — Shared constants
 *
 * Source of truth for step names, event names, and defaults.
 */
/** The 7-step prediction pipeline names (1-indexed). */
export declare const STEP_NAMES: readonly string[];
/** Total number of pipeline steps. */
export declare const TOTAL_STEPS = 7;
/** NDJSON event names. */
export declare const EVENTS: {
    readonly RUN_START: "run:start";
    readonly STEP_START: "step:start";
    readonly STEP_PROGRESS: "step:progress";
    readonly STEP_DONE: "step:done";
    readonly RUN_DONE: "run:done";
    readonly RUN_ERROR: "run:error";
    readonly RUN_CANCELLED: "run:cancelled";
};
/** NDJSON payload version for forward compatibility. */
export declare const PAYLOAD_VERSION = 1;
/** Default poll intervals (ms). */
export declare const POLL_INTERVAL = 15000;
export declare const REPORT_POLL_INTERVAL = 5000;
export declare const MAX_POLL_MINUTES = 60;
/** Default seed text expansion threshold (chars). */
export declare const SEED_EXPAND_THRESHOLD = 200;
/** Default RunManager config values. */
export declare const DEFAULTS: {
    readonly maxConcurrent: 2;
    readonly runTimeout: number;
    readonly dedupeWindow: number;
    readonly idempotencyTTL: number;
};

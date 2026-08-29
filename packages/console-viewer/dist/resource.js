import { useCallback, useEffect, useState } from "react";
export function useResource(load, keys) {
    const [reload, setReload] = useState(0);
    const [state, setState] = useState({ status: "loading" });
    useEffect(() => {
        const controller = new AbortController();
        setState({ status: "loading" });
        void load(controller.signal).then((value) => { if (!controller.signal.aborted)
            setState({ status: "ready", value }); }, (error) => { if (!controller.signal.aborted)
            setState({ status: "error", error: error instanceof Error ? error : new Error("Request failed.") }); });
        return () => controller.abort();
        // Callers provide stable route scalars and memoized gateways.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [...keys, reload]);
    return { state, retry: useCallback(() => setReload((value) => value + 1), []) };
}
//# sourceMappingURL=resource.js.map
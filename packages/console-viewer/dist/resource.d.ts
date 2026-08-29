export type ResourceState<T> = {
    status: "loading";
} | {
    status: "ready";
    value: T;
} | {
    status: "error";
    error: Error;
};
export declare function useResource<T>(load: (signal: AbortSignal) => Promise<T>, keys: readonly unknown[]): {
    state: ResourceState<T>;
    retry: () => void;
};
//# sourceMappingURL=resource.d.ts.map
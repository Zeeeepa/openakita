/**
 * 全局 fetch 拦截：macOS WKWebView 的 fetch() 遵守系统代理设置，
 * 代理软件（Clash/V2Ray 等）运行时，对 127.0.0.1 的请求会被路由到
 * 代理服务器而非直连本地后端。
 *
 * 解决方案：在 Tauri 环境下，用 Tauri HTTP 插件的 fetch() 替代原生 fetch()。
 * 插件走 Rust reqwest，配合 Rust 端设置的 NO_PROXY 环境变量绕过系统代理。
 * 支持 JSON、FormData、SSE 流式响应，与原生 fetch 行为一致。
 *
 * 仅拦截 localhost 请求，其他请求仍走浏览器原生 fetch。
 * 在非 Tauri 环境（如 `npm run dev` 的浏览器）下不做任何拦截。
 */
import { fetch as tauriFetch } from "@tauri-apps/plugin-http";

const LOCAL_RE = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(?:\/|$)/;

export function installLocalFetchOverride(): void {
  // Only intercept in Tauri desktop runtime.
  // In browser dev server (`npm run dev`), Tauri IPC bridge doesn't exist
  // and the plugin would throw — skip entirely so native fetch works as-is.
  if (
    typeof window === "undefined" ||
    !("__TAURI_INTERNALS__" in window)
  ) {
    return;
  }

  const nativeFetch = window.fetch.bind(window);

  window.fetch = async function (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    let url: string;
    if (typeof input === "string") url = input;
    else if (input instanceof URL) url = input.toString();
    else if (input instanceof Request) url = input.url;
    else return nativeFetch(input, init);

    if (!LOCAL_RE.test(url)) {
      return nativeFetch(input, init);
    }

    // Route through Tauri HTTP plugin (Rust reqwest + NO_PROXY env).
    // No fallback to native fetch: on macOS with proxy software, native fetch
    // also goes through WebKit system proxy and would fail the same way.
    // Errors (connection refused, timeout, etc.) propagate to the caller.
    return tauriFetch(input, init);
  };
}

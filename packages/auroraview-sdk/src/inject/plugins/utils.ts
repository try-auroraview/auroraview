/**
 * Plugin utilities shared across all plugins
 */

/**
 * Invoke a plugin command
 */
export async function invokePlugin<T = unknown>(
  plugin: string,
  command: string,
  args?: Record<string, unknown>
): Promise<T> {
  if (!window.auroraview || !window.auroraview.invoke) {
    throw new Error('AuroraView bridge not available');
  }

  const result = await window.auroraview.invoke<T & { success?: boolean; error?: string; code?: string }>(
    `plugin:${plugin}|${command}`,
    args || {}
  );

  if (result && result.success === false) {
    const error = new Error(result.error || 'Unknown error') as Error & { code?: string };
    error.code = result.code || 'UNKNOWN';
    throw error;
  }

  return result;
}

/**
 * Attach a plugin to the auroraview object
 */
export function attachPlugin(name: string, api: Record<string, unknown>): void {
  if (window.auroraview) {
    (window.auroraview as unknown as Record<string, unknown>)[name] = api;
    console.log(`[AuroraView] ${name.charAt(0).toUpperCase() + name.slice(1)} plugin initialized`);
  }
}

/**
 * Wait for auroraview to be available and attach plugin
 */
export function initPlugin(name: string, api: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;
  if (window.auroraview) {
    attachPlugin(name, api);
  } else {
    const observer = setInterval(function () {
      if (window.auroraview) {
        clearInterval(observer);
        attachPlugin(name, api);
      }
    }, 10);

    // Stop trying after 5 seconds
    setTimeout(function () {
      clearInterval(observer);
    }, 5000);
  }
}

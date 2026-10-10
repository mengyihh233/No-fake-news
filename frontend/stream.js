'use strict';

// The request owner decides whether to retry. This reader never starts a request.
(() => {
  const stages = ['queued', 'planning', 'searching', 'reading', 'supplemental_search', 'analyzing', 'checking', 'repairing', 'capturing', 'complete'];
  class StreamError extends Error {
    constructor(code, message = '') { super(message); this.name = 'StreamError'; this.code = code; }
  }
  async function readResearchStream(body, { signal, onProgress = () => {}, frameLimit = 4 * 1024 * 1024, totalLimit = 16 * 1024 * 1024 } = {}) {
    if (!body?.getReader) throw new StreamError('unavailable');
    const reader = body.getReader();
    const decoder = new TextDecoder('utf-8', { fatal: true });
    const encoder = new TextEncoder();
    let buffer = '', received = 0, terminal = null, result = null, error = null;
    const aborted = () => { const failure = new Error('Aborted'); failure.name = 'AbortError'; return failure; };
    const cancel = () => { Promise.resolve(reader.cancel()).catch(() => {}); };
    signal?.addEventListener('abort', cancel, { once: true });
    const frame = text => {
      if (encoder.encode(text).byteLength > frameLimit) throw new StreamError('limit');
      let event = 'message'; const data = [];
      for (const line of text.split(/\r?\n/)) {
        if (line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon < 0 ? line : line.slice(0, colon);
        let value = colon < 0 ? '' : line.slice(colon + 1);
        if (value.startsWith(' ')) value = value.slice(1);
        if (field === 'event') event = value;
        else if (field === 'data') data.push(value);
      }
      if (!data.length || !['progress', 'result', 'error'].includes(event)) return;
      if (terminal) throw new StreamError('duplicate_terminal');
      let payload;
      try { payload = JSON.parse(data.join('\n')); } catch { throw new StreamError('invalid'); }
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new StreamError('invalid');
      if (event === 'progress') {
        if (!stages.includes(payload.stage) || !Number.isInteger(payload.completed) || payload.completed < 0 || (payload.total !== null && (!Number.isInteger(payload.total) || payload.total < 0 || payload.completed > payload.total))) throw new StreamError('invalid');
        onProgress({ stage: payload.stage, completed: payload.completed, total: payload.total });
      } else if (event === 'result') {
        if (!Array.isArray(payload.evidence) || !Array.isArray(payload.claims)) throw new StreamError('invalid');
        terminal = event; result = payload;
      } else {
        if (typeof payload.error?.code !== 'string' || typeof payload.error?.message !== 'string') throw new StreamError('invalid');
        terminal = event; error = new StreamError('server', payload.error.message.slice(0, 1400));
      }
    };
    try {
      while (true) {
        if (signal?.aborted) throw aborted();
        const chunk = await reader.read();
        if (signal?.aborted) throw aborted();
        if (chunk.done) { buffer += decoder.decode(); break; }
        received += chunk.value.byteLength;
        if (received > totalLimit) throw new StreamError('limit');
        buffer += decoder.decode(chunk.value, { stream: true });
        let match;
        while ((match = /\r?\n\r?\n/.exec(buffer))) {
          frame(buffer.slice(0, match.index));
          buffer = buffer.slice(match.index + match[0].length);
        }
        if (encoder.encode(buffer).byteLength > frameLimit) throw new StreamError('limit');
      }
      // SSE dispatches complete frames only; an unterminated data frame is incomplete.
      if (buffer.trim() && !buffer.split(/\r?\n/).every(line => !line || line.startsWith(':'))) throw new StreamError('incomplete');
      if (!terminal) throw new StreamError('incomplete');
      if (error) throw error;
      return result;
    } catch (failure) {
      cancel();
      if (signal?.aborted) throw aborted();
      if (failure instanceof TypeError) throw new StreamError('invalid');
      throw failure;
    } finally {
      signal?.removeEventListener('abort', cancel);
      reader.releaseLock();
    }
  }
  const api = { readResearchStream, stages, StreamError };
  globalThis.NoFakeNewsStream = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();

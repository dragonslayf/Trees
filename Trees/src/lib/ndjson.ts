/**
 * 消费 FastAPI 返回的 application/x-ndjson 流，每行一条 JSON 对象。
 */
export async function forEachNdjsonObject(
  body: ReadableStream<Uint8Array> | null | undefined,
  onObject: (obj: Record<string, unknown>) => void,
): Promise<void> {
  if (!body) throw new Error('无法读取响应流')

  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        onObject(JSON.parse(line) as Record<string, unknown>)
      } catch (e) {
        if (e instanceof SyntaxError) continue
        throw e
      }
    }
  }
  if (buffer.trim()) {
    try {
      onObject(JSON.parse(buffer.trim()) as Record<string, unknown>)
    } catch (e) {
      if (!(e instanceof SyntaxError)) throw e
    }
  }
}

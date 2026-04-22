/**
 * DOM 切分 ensure + 原始切片画廊路径（与数据管理 / 单木分割「原始数据」共用）。
 */
export async function ensureDomTilesAndGalleryPath(
  api: (path: string) => string,
  opts: { data_dir: string; dom_filename: string },
): Promise<{ data_dir: string; dom_filename: string; tilesGalleryPath: string }> {
  const params = new URLSearchParams()
  params.set('data_dir', opts.data_dir)
  params.set('dom_filename', opts.dom_filename)
  const ensureUrl = api(`/api/tiles/ensure?${params.toString()}`)
  const r = await fetch(ensureUrl, { method: 'POST', credentials: 'include' })
  const data = (await r.json().catch(() => ({}))) as {
    detail?: string
    dom_filename?: string
    data_dir?: string
  }
  if (!r.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : r.statusText)
  }
  const dom =
    typeof data.dom_filename === 'string' && data.dom_filename.trim()
      ? data.dom_filename.trim()
      : opts.dom_filename
  const galleryParams = new URLSearchParams()
  galleryParams.set('dom_filename', dom)
  const dd = data.data_dir ?? opts.data_dir
  if (dd) galleryParams.set('data_dir', dd)
  const galleryQs = galleryParams.toString()
  const tilesGalleryPath = galleryQs ? `/api/tiles/gallery?${galleryQs}` : '/api/tiles/gallery'
  return { data_dir: dd, dom_filename: dom, tilesGalleryPath }
}

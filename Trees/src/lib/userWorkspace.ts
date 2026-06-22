/** 上传清单中记录的文件角色。 */
export type UploadManifest = {
  dom?: string
  chm?: string
  csv?: string
}

function isTif(filename: string): boolean {
  return /\.(tif|tiff)$/i.test(filename)
}

function looksLikeChmFilename(filename: string): boolean {
  return /(?:^|[_\-.])chm(?:[_\-.]|$)/i.test(filename)
}

/**
 * 在用户目录文件列表中选取用于分割的 DOM：
 * 1) 优先使用上传清单中的 dom；
 * 2) 否则在 GeoTIFF 中排除 CHM（manifest.chm 与命名规则）；
 * 3) 兜底返回字典序第一个 GeoTIFF。
 */
export function pickDomFromFiles(files: string[], manifest?: UploadManifest): string | null {
  const tifs = files.filter(isTif).sort()
  if (!tifs.length) return null

  const manifestDom = manifest?.dom?.trim()
  if (manifestDom && tifs.includes(manifestDom)) return manifestDom

  const chmSet = new Set<string>()
  const manifestChm = manifest?.chm?.trim()
  if (manifestChm && tifs.includes(manifestChm)) chmSet.add(manifestChm)
  for (const f of tifs) {
    if (looksLikeChmFilename(f)) chmSet.add(f)
  }

  const domCandidates = tifs.filter((f) => !chmSet.has(f))
  return domCandidates.length ? domCandidates[0]! : tifs[0]!
}

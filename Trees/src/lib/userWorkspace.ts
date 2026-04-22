/** 在用户目录文件列表中选取用于分割的 DOM（优先字典序第一个 GeoTIFF） */
export function pickDomFromFiles(files: string[]): string | null {
  const tifs = files.filter((f) => /\.(tif|tiff)$/i.test(f)).sort()
  return tifs.length ? tifs[0]! : null
}

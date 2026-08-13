const VIEWPORT_TOLERANCE = 1
const SCALE_TOLERANCE = 0.01

export function resolveChatViewport({
  layoutHeight,
  viewportHeight,
  viewportOffsetTop,
  viewportScale
}) {
  const hasViewport = Number.isFinite(viewportHeight) && viewportHeight > 0
  const height = hasViewport ? viewportHeight : null
  const offsetTop = Number.isFinite(viewportOffsetTop) ? viewportOffsetTop : 0
  const scale = Number.isFinite(viewportScale) ? viewportScale : 1
  const isZoomed = Math.abs(scale - 1) > SCALE_TOLERANCE
  const heightReduced =
    Number.isFinite(layoutHeight) &&
    layoutHeight - viewportHeight > VIEWPORT_TOLERANCE
  const viewportPanned = offsetTop > VIEWPORT_TOLERANCE

  return {
    constrained: hasViewport && !isZoomed && (heightReduced || viewportPanned),
    height,
    offsetTop
  }
}

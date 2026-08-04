import { readFileSync } from 'node:fs'
import { inflateSync } from 'node:zlib'

const PNG_SIGNATURE = Buffer.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a
])
const RGBA_BYTES_PER_PIXEL = 4

const paethPredictor = (left, above, upperLeft) => {
  const estimate = left + above - upperLeft
  const leftDistance = Math.abs(estimate - left)
  const aboveDistance = Math.abs(estimate - above)
  const upperLeftDistance = Math.abs(estimate - upperLeft)

  if (leftDistance <= aboveDistance && leftDistance <= upperLeftDistance) {
    return left
  }
  if (aboveDistance <= upperLeftDistance) {
    return above
  }
  return upperLeft
}

const reconstructByte = (filter, value, left, above, upperLeft) => {
  const predictors = [
    0,
    left,
    above,
    Math.floor((left + above) / 2),
    paethPredictor(left, above, upperLeft)
  ]

  if (filter < 0 || filter >= predictors.length) {
    throw new Error(`Unsupported PNG filter type: ${filter}`)
  }
  return (value + predictors[filter]) & 0xff
}

export const decodeRgbaPng = (path) => {
  const source = readFileSync(path)
  if (!source.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
    throw new Error(`Invalid PNG signature: ${path}`)
  }

  const compressedChunks = []
  let bitDepth = null
  let colorType = null
  let height = null
  let interlaceMethod = null
  let offset = PNG_SIGNATURE.length
  let width = null

  while (offset < source.length) {
    const length = source.readUInt32BE(offset)
    const type = source.toString('ascii', offset + 4, offset + 8)
    const dataStart = offset + 8
    const dataEnd = dataStart + length
    const chunk = source.subarray(dataStart, dataEnd)

    if (type === 'IHDR') {
      width = chunk.readUInt32BE(0)
      height = chunk.readUInt32BE(4)
      bitDepth = chunk[8]
      colorType = chunk[9]
      interlaceMethod = chunk[12]
    } else if (type === 'IDAT') {
      compressedChunks.push(chunk)
    } else if (type === 'IEND') {
      break
    }

    offset = dataEnd + 4
  }

  if (
    width === null ||
    height === null ||
    bitDepth !== 8 ||
    colorType !== 6 ||
    interlaceMethod !== 0
  ) {
    throw new Error(`Expected a non-interlaced 8-bit RGBA PNG: ${path}`)
  }

  const inflated = inflateSync(Buffer.concat(compressedChunks))
  const rowBytes = width * RGBA_BYTES_PER_PIXEL
  const expectedLength = height * (rowBytes + 1)
  if (inflated.length !== expectedLength) {
    throw new Error(`Unexpected decompressed PNG length: ${path}`)
  }

  const pixels = Buffer.alloc(width * height * RGBA_BYTES_PER_PIXEL)
  let sourceOffset = 0

  for (let row = 0; row < height; row += 1) {
    const filter = inflated[sourceOffset]
    sourceOffset += 1
    const rowOffset = row * rowBytes
    const previousRowOffset = rowOffset - rowBytes

    for (let column = 0; column < rowBytes; column += 1) {
      const left =
        column >= RGBA_BYTES_PER_PIXEL
          ? pixels[rowOffset + column - RGBA_BYTES_PER_PIXEL]
          : 0
      const above = row > 0 ? pixels[previousRowOffset + column] : 0
      const upperLeft =
        row > 0 && column >= RGBA_BYTES_PER_PIXEL
          ? pixels[previousRowOffset + column - RGBA_BYTES_PER_PIXEL]
          : 0
      pixels[rowOffset + column] = reconstructByte(
        filter,
        inflated[sourceOffset + column],
        left,
        above,
        upperLeft
      )
    }

    sourceOffset += rowBytes
  }

  return { data: pixels, height, width }
}

const findAccentMask = (image) => {
  const pixelCount = image.width * image.height
  const candidates = new Uint8Array(pixelCount)
  const visited = new Uint8Array(pixelCount)
  let largestComponent = []

  for (let pixel = 0; pixel < pixelCount; pixel += 1) {
    const offset = pixel * RGBA_BYTES_PER_PIXEL
    const red = image.data[offset]
    const green = image.data[offset + 1]
    const blue = image.data[offset + 2]
    const alpha = image.data[offset + 3]

    if (alpha > 0 && blue >= red + 10 && blue >= green + 10) {
      candidates[pixel] = 1
    }
  }

  for (let start = 0; start < pixelCount; start += 1) {
    if (!candidates[start] || visited[start]) {
      continue
    }

    const component = []
    const stack = [start]
    visited[start] = 1

    while (stack.length > 0) {
      const pixel = stack.pop()
      component.push(pixel)
      const x = pixel % image.width
      const y = Math.floor(pixel / image.width)

      for (let yOffset = -1; yOffset <= 1; yOffset += 1) {
        for (let xOffset = -1; xOffset <= 1; xOffset += 1) {
          if (xOffset === 0 && yOffset === 0) {
            continue
          }

          const neighborX = x + xOffset
          const neighborY = y + yOffset
          if (
            neighborX < 0 ||
            neighborX >= image.width ||
            neighborY < 0 ||
            neighborY >= image.height
          ) {
            continue
          }

          const neighbor = neighborY * image.width + neighborX
          if (candidates[neighbor] && !visited[neighbor]) {
            visited[neighbor] = 1
            stack.push(neighbor)
          }
        }
      }
    }

    if (component.length > largestComponent.length) {
      largestComponent = component
    }
  }

  const accentMask = new Uint8Array(pixelCount)
  for (const pixel of largestComponent) {
    accentMask[pixel] = 1
  }
  return accentMask
}

export const inspectThemedLogoPair = (lightPath, darkPath) => {
  const light = decodeRgbaPng(lightPath)
  const dark = decodeRgbaPng(darkPath)
  let alphaMismatchCount = 0

  if (light.width !== dark.width || light.height !== dark.height) {
    return {
      alphaMismatchCount: Number.POSITIVE_INFINITY,
      accentMismatchCount: Number.POSITIVE_INFINITY,
      accentPixelCount: 0,
      darkHeight: dark.height,
      darkWidth: dark.width,
      lightHeight: light.height,
      lightWidth: light.width,
      visibleBodyMismatchCount: Number.POSITIVE_INFINITY,
      visibleBodyPixelCount: 0
    }
  }

  const accentMask = findAccentMask(light)
  let accentMismatchCount = 0
  let accentPixelCount = 0
  let visibleBodyMismatchCount = 0
  let visibleBodyPixelCount = 0

  for (let offset = 0; offset < light.data.length; offset += 4) {
    const pixel = offset / RGBA_BYTES_PER_PIXEL
    const lightAlpha = light.data[offset + 3]
    const darkAlpha = dark.data[offset + 3]
    if (lightAlpha !== darkAlpha) {
      alphaMismatchCount += 1
    }
    if (darkAlpha === 0) {
      continue
    }

    if (accentMask[pixel]) {
      accentPixelCount += 1
      if (
        !light.data
          .subarray(offset, offset + 4)
          .equals(dark.data.subarray(offset, offset + 4))
      ) {
        accentMismatchCount += 1
      }
      continue
    }

    visibleBodyPixelCount += 1
    if (
      dark.data[offset] !== 255 ||
      dark.data[offset + 1] !== 255 ||
      dark.data[offset + 2] !== 255
    ) {
      visibleBodyMismatchCount += 1
    }
  }

  return {
    alphaMismatchCount,
    accentMismatchCount,
    accentPixelCount,
    darkHeight: dark.height,
    darkWidth: dark.width,
    lightHeight: light.height,
    lightWidth: light.width,
    visibleBodyMismatchCount,
    visibleBodyPixelCount
  }
}

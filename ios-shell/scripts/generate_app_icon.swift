import AppKit
import CoreGraphics

let size = 1024
let colorSpace = CGColorSpaceCreateDeviceRGB()
guard let context = CGContext(
    data: nil,
    width: size,
    height: size,
    bitsPerComponent: 8,
    bytesPerRow: size * 4,
    space: colorSpace,
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
) else {
    fatalError("Unable to create icon context")
}

context.setFillColor(CGColor(red: 0.23, green: 0.36, blue: 0.29, alpha: 1))
context.fill(CGRect(x: 0, y: 0, width: size, height: size))
context.translateBy(x: 0, y: CGFloat(size))
context.scaleBy(x: 1, y: -1)

context.setStrokeColor(CGColor(red: 0.98, green: 0.97, blue: 0.94, alpha: 1))
context.setLineWidth(78)
context.setLineCap(.round)
context.setLineJoin(.round)
context.beginPath()
context.move(to: CGPoint(x: 214, y: 494))
context.addLine(to: CGPoint(x: 512, y: 246))
context.addLine(to: CGPoint(x: 810, y: 494))
context.move(to: CGPoint(x: 286, y: 454))
context.addLine(to: CGPoint(x: 286, y: 760))
context.addLine(to: CGPoint(x: 738, y: 760))
context.addLine(to: CGPoint(x: 738, y: 454))
context.strokePath()

let heart = CGMutablePath()
heart.move(to: CGPoint(x: 512, y: 694))
heart.addCurve(
    to: CGPoint(x: 402, y: 554),
    control1: CGPoint(x: 486, y: 655),
    control2: CGPoint(x: 402, y: 612)
)
heart.addCurve(
    to: CGPoint(x: 512, y: 500),
    control1: CGPoint(x: 402, y: 486),
    control2: CGPoint(x: 477, y: 477)
)
heart.addCurve(
    to: CGPoint(x: 622, y: 554),
    control1: CGPoint(x: 547, y: 477),
    control2: CGPoint(x: 622, y: 486)
)
heart.addCurve(
    to: CGPoint(x: 512, y: 694),
    control1: CGPoint(x: 622, y: 612),
    control2: CGPoint(x: 538, y: 655)
)
heart.closeSubpath()
context.addPath(heart)
context.setFillColor(CGColor(red: 0.94, green: 0.43, blue: 0.34, alpha: 1))
context.fillPath()

guard let image = context.makeImage() else {
    fatalError("Unable to render icon")
}
let bitmap = NSBitmapImageRep(cgImage: image)
guard let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Unable to encode icon")
}
let output = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? "AppIcon-1024.png")
try png.write(to: output)

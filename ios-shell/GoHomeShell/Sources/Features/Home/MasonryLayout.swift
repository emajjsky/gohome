import SwiftUI

struct MasonryLayout: Layout {
    var spacing: CGFloat = 12

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        guard let width = proposal.width, width > 0 else { return .zero }
        let columnWidth = max(0, (width - spacing) / 2)
        var heights = [CGFloat](repeating: 0, count: 2)
        for subview in subviews {
            let column = heights[0] <= heights[1] ? 0 : 1
            let size = subview.sizeThatFits(ProposedViewSize(width: columnWidth, height: nil))
            heights[column] += size.height + spacing
        }
        return CGSize(width: width, height: max((heights.max() ?? 0) - spacing, 0))
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        let columnWidth = max(0, (bounds.width - spacing) / 2)
        var heights = [CGFloat](repeating: bounds.minY, count: 2)
        for subview in subviews {
            let column = heights[0] <= heights[1] ? 0 : 1
            let size = subview.sizeThatFits(ProposedViewSize(width: columnWidth, height: nil))
            let x = bounds.minX + CGFloat(column) * (columnWidth + spacing)
            subview.place(
                at: CGPoint(x: x, y: heights[column]),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: columnWidth, height: size.height)
            )
            heights[column] += size.height + spacing
        }
    }
}

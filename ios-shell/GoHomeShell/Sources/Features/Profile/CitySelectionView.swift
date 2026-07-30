import SwiftUI

struct CitySelectionView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var selection: String
    @State private var query = ""

    private let cities = [
        "北京市", "上海市", "天津市", "重庆市", "广州市", "深圳市", "杭州市", "南京市", "苏州市", "成都市",
        "武汉市", "西安市", "长沙市", "郑州市", "青岛市", "宁波市", "厦门市", "福州市", "济南市", "合肥市",
        "昆明市", "南宁市", "海口市", "石家庄市", "太原市", "沈阳市", "大连市", "长春市", "哈尔滨市", "兰州市",
        "贵阳市", "南昌市", "无锡市", "温州市", "佛山市", "东莞市", "珠海市", "中山市", "泉州市", "烟台市",
    ]

    var body: some View {
        NavigationStack {
            List(filteredCities, id: \.self) { city in
                Button {
                    selection = city
                    dismiss()
                } label: {
                    HStack {
                        Text(city).foregroundStyle(GoHomeTheme.ink)
                        Spacer()
                        if selection == city {
                            Image(systemName: "checkmark")
                                .font(.system(size: 13, weight: .bold))
                                .foregroundStyle(GoHomeTheme.ginger)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .listStyle(.plain)
            .accessibilityIdentifier("city-selection-list")
            .searchable(text: $query, prompt: "搜索城市")
            .navigationTitle("选择城市")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
        }
    }

    private var filteredCities: [String] {
        let normalized = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? cities : cities.filter { $0.localizedCaseInsensitiveContains(normalized) }
    }
}

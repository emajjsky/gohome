import XCTest
@testable import GoHomeShell

final class EventPresentationTests: XCTestCase {
    func testSegmentsMapToUserActions() {
        XCTAssertEqual(EventPresentation.segment(event()), .pending)
        XCTAssertEqual(EventPresentation.segment(event(acknowledged: true, resolution: "handled")), .handled)
        XCTAssertEqual(EventPresentation.segment(event(acknowledged: true, resolution: "false_positive")), .falsePositive)
    }

    func testVerificationCopyIsHumanReadableAndHidesRawMetrics() {
        let text = EventPresentation.verificationText(
            EventVerification(status: "confirmed", result: EventVerificationResult(reason: "画面证据支持异常判断")),
            evidenceCount: 3
        )

        XCTAssertTrue(text.contains("云端复核"))
        XCTAssertTrue(text.contains("3 张证据"))
        XCTAssertFalse(text.contains("fall_score"))
        XCTAssertFalse(text.contains("threshold"))
    }

    func testSafetyEventLabelsDoNotExposeEngineeringNames() {
        XCTAssertEqual(EventPresentation.label(for: "fall_candidate"), "疑似跌倒")
        XCTAssertEqual(EventPresentation.label(for: "prolonged_floor_lying"), "长时间倒地")
        XCTAssertEqual(EventPresentation.label(for: "camera_offline"), "设备离线")
    }

    func testRelatedCameraEventsBecomeOneEvidenceGroup() {
        let primary = event(
            id: "primary",
            payload: EventPayload(incident: EventIncident(primaryEventID: "primary", sourceCameraIDs: ["2", "3"]))
        )
        let related = event(
            id: "related",
            cameraID: "3",
            payload: EventPayload(incident: EventIncident(primaryEventID: "primary", sourceCameraIDs: ["2", "3"]))
        )

        let groups = EventPresentation.groups([primary, related], segment: .pending)
        XCTAssertEqual(groups.count, 1)
        XCTAssertEqual(groups[0].cameraCount, 2)
        XCTAssertEqual(groups[0].related.map(\.id), ["related"])
    }

    func testTimelineIncludesCloudReviewAndMultiCameraEvidence() {
        let value = event(
            payload: EventPayload(
                incident: EventIncident(primaryEventID: "1", sourceCameraIDs: ["2", "3"]),
                verification: EventVerification(status: "uncertain")
            )
        )

        let titles = EventPresentation.timeline(for: value).map(\.title)
        XCTAssertTrue(titles.contains("家庭盒子发现异常"))
        XCTAssertTrue(titles.contains("云端证据不足"))
        XCTAssertTrue(titles.contains("多路画面提供佐证"))
    }

    func testDecodesBareCloudSummaryAndKeepsDynamicPayloadSafe() throws {
        let data = Data(#"""
        {
            "id": 200,
            "type": "fall_candidate",
            "event_type": "fall_candidate",
            "level": "critical",
            "room": "客厅",
            "camera_id": 2,
            "camera_name": "客厅摄像头",
            "occurred_at": "2026-07-22T09:30:00+08:00",
            "created_at": "2026-07-22T09:30:00+08:00",
            "acknowledged": false,
            "resolution": "",
            "media_asset_id": 1,
            "evidence_media": [{"asset_id": 1, "role": "current", "captured_at": "2026-07-22T09:30:00+08:00", "postures": []}],
            "payload": {"verification": {"status": "pending", "decision": ""}, "incident": {"source_camera_ids": [2, 3]}}
        }
        """#.utf8)

        let value = try JSONDecoder().decode(AppEvent.self, from: data)
        XCTAssertEqual(value.id, "200")
        XCTAssertEqual(value.cameraID, "2")
        XCTAssertEqual(value.mediaAssetID, "1")
        XCTAssertEqual(value.evidenceMedia.count, 1)
        XCTAssertEqual(value.payload.incident?.sourceCameraIDs, ["2", "3"])
        XCTAssertEqual(value.payload.verification?.status, "pending")
    }

    private func event(
        id: String = "1",
        cameraID: String = "2",
        acknowledged: Bool = false,
        resolution: String = "",
        payload: EventPayload = EventPayload()
    ) -> AppEvent {
        AppEvent(
            id: id,
            type: "fall_candidate",
            level: "critical",
            room: "客厅",
            cameraID: cameraID,
            cameraName: "客厅摄像头",
            occurredAt: "2026-07-22T09:30:00+08:00",
            createdAt: "2026-07-22T09:30:00+08:00",
            updatedAt: "2026-07-22T09:30:00+08:00",
            acknowledged: acknowledged,
            resolution: resolution,
            payload: payload
        )
    }
}

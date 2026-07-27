import Foundation

struct OnboardingService: Sendable {
    let client: APIClient

    func createFamily(name: String) async throws -> AppFamily {
        let body = try JSONEncoder().encode(["name": name])
        return try await client.send(Endpoint<AppFamily>(method: .post, path: "/api/families", body: body))
    }

    func joinFamily(code: String) async throws -> AppFamily {
        let endpoint: Endpoint<FamilyInvitationConsumeResponse> = try .jsonBody(
            method: .post,
            path: "/api/v2/family-invitations/consume",
            body: FamilyInvitationConsumeRequest(code: code)
        )
        let response = try await client.send(endpoint)
        guard response.joined else { throw APIError.invalidResponse }
        return response.family
    }

    func saveProfile(familyID: String, elderID: String = "elder_primary", profile: ProfilePayload) async throws -> ElderProfile {
        let body = try JSONEncoder().encode(profile)
        return try await client.send(Endpoint<ElderProfile>(method: .put, path: "/api/v1/families/\(familyID)/elders/\(elderID)/profile", body: body))
    }

    func availableDevices(familyID: String) async throws -> [ClaimableDevice] {
        try await client.send(Endpoint<[ClaimableDevice]>(
            path: "/api/device-claims/available",
            queryItems: [URLQueryItem(name: "family_id", value: familyID)]
        ))
    }

    func bindings(familyID: String) async throws -> [DeviceBinding] {
        try await client.send(Endpoint<[DeviceBinding]>(
            path: "/api/device-bindings",
            queryItems: [URLQueryItem(name: "family_id", value: familyID)]
        ))
    }

    func createBindingCode(familyID: String) async throws -> DeviceBindingCode {
        let payload = BindingCodePayload(familyID: familyID, expiresInMinutes: 10, note: "native iOS LAN pairing")
        let body = try JSONEncoder().encode(payload)
        return try await client.send(Endpoint<DeviceBindingCode>(method: .post, path: "/api/device/binding-codes", body: body))
    }

    var pairReturnURL: URL { client.baseURL }

    func claimDevice(familyID: String, device: DiscoveredBox) async throws -> DeviceClaimResponse {
        let payload = DeviceClaimPayload(
            familyID: familyID,
            deviceID: device.deviceID,
            serialNumber: device.serialNumber,
            claimCode: device.claimCode ?? device.serialNumber ?? device.deviceID
        )
        let body = try JSONEncoder().encode(payload)
        return try await client.send(Endpoint<DeviceClaimResponse>(method: .post, path: "/api/device-claims/claim", body: body))
    }

    func saveCamera(
        familyID: String,
        deviceID: String,
        name: String,
        room: String,
        streamURL: String,
        username: String,
        password: String
    ) async throws -> CameraConfig {
        let payload = CameraPayload(
            familyID: familyID,
            deviceID: deviceID,
            name: name,
            room: room,
            streamURL: streamURL,
            username: username,
            password: password
        )
        let body = try JSONEncoder().encode(payload)
        return try await client.send(Endpoint<CameraConfig>(method: .post, path: "/api/cameras", body: body))
    }
}

struct ProfilePayload: Encodable, Sendable {
    let displayName: String
    let relationship: String
    let city: String
    let district: String
    let phone: String
    let mobilePhone: String
    let homePhone: String

    enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case relationship, city, district, phone
        case mobilePhone = "mobile_phone"
        case homePhone = "home_phone"
    }
}

private struct DeviceClaimPayload: Encodable, Sendable {
    let familyID: String
    let deviceID: String
    let serialNumber: String?
    let claimCode: String

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
        case deviceID = "device_id"
        case serialNumber = "serial_number"
        case claimCode = "claim_code"
    }
}

private struct BindingCodePayload: Encodable, Sendable {
    let familyID: String
    let expiresInMinutes: Int
    let note: String

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
        case expiresInMinutes = "expires_in_minutes"
        case note
    }
}

private struct CameraPayload: Encodable, Sendable {
    let familyID: String
    let deviceID: String
    let name: String
    let room: String
    let streamURL: String
    let username: String
    let password: String

    enum CodingKeys: String, CodingKey {
        case familyID = "family_id"
        case deviceID = "device_id"
        case name, room, username, password
        case streamURL = "stream_url"
    }
}

package pl.akmf.ksef.sdk.client.model.session.online;

import java.time.OffsetDateTime;

public class OpenOnlineSessionResponse {
    private String referenceNumber;

    private OffsetDateTime validUntil;

    public OpenOnlineSessionResponse() {
    }

    public OpenOnlineSessionResponse(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public void setReferenceNumber(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public OffsetDateTime getValidUntil() {
        return validUntil;
    }

    public void setValidUntil(OffsetDateTime validUntil) {
        this.validUntil = validUntil;
    }
}


package pl.akmf.ksef.sdk.client.model.certificate;

import java.time.OffsetDateTime;

public class CertificateEnrollmentResponse {
    private String referenceNumber;
    private OffsetDateTime timestamp;

    public CertificateEnrollmentResponse() {
    }

    public CertificateEnrollmentResponse(String referenceNumber, OffsetDateTime timestamp) {
        this.referenceNumber = referenceNumber;
        this.timestamp = timestamp;
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public void setReferenceNumber(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public OffsetDateTime getTimestamp() {
        return timestamp;
    }

    public void setTimestamp(OffsetDateTime timestamp) {
        this.timestamp = timestamp;
    }
}


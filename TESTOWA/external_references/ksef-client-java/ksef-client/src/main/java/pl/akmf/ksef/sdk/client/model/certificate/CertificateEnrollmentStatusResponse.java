package pl.akmf.ksef.sdk.client.model.certificate;

import pl.akmf.ksef.sdk.client.model.StatusInfo;

import java.time.OffsetDateTime;

public class CertificateEnrollmentStatusResponse {
    private OffsetDateTime requestDate;
    private StatusInfo status;
    private String certificateSerialNumber;

    public CertificateEnrollmentStatusResponse() {
    }

    public CertificateEnrollmentStatusResponse(OffsetDateTime requestDate, StatusInfo status, String certificateSerialNumber) {
        this.requestDate = requestDate;
        this.status = status;
        this.certificateSerialNumber = certificateSerialNumber;
    }

    public OffsetDateTime getRequestDate() {
        return requestDate;
    }

    public void setRequestDate(OffsetDateTime requestDate) {
        this.requestDate = requestDate;
    }

    public StatusInfo getStatus() {
        return status;
    }

    public void setStatus(StatusInfo status) {
        this.status = status;
    }

    public String getCertificateSerialNumber() {
        return certificateSerialNumber;
    }

    public void setCertificateSerialNumber(String certificateSerialNumber) {
        this.certificateSerialNumber = certificateSerialNumber;
    }
}


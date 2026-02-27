package pl.akmf.ksef.sdk.client.model.certificate;

import java.util.List;

public class CertificateListRequest {
    private List<String> certificateSerialNumbers;

    public CertificateListRequest() {
    }

    public CertificateListRequest(List<String> certificateSerialNumbers) {
        this.certificateSerialNumbers = certificateSerialNumbers;
    }

    public List<String> getCertificateSerialNumbers() {
        return certificateSerialNumbers;
    }

    public void setCertificateSerialNumbers(List<String> certificateSerialNumbers) {
        this.certificateSerialNumbers = certificateSerialNumbers;
    }
}


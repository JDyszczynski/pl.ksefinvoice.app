package pl.akmf.ksef.sdk.client.model.certificate;

public class SendCertificateEnrollmentRequest {
    private String certificateName;
    private byte[] csr;
    private String validFrom;
    private CertificateType certificateType;

    public SendCertificateEnrollmentRequest() {
    }

    public SendCertificateEnrollmentRequest(String certificateName, byte[] csr, String validFrom, CertificateType certificateType) {
        this.certificateName = certificateName;
        this.csr = csr;
        this.validFrom = validFrom;
        this.certificateType = certificateType;
    }

    public String getCertificateName() {
        return certificateName;
    }

    public void setCertificateName(String certificateName) {
        this.certificateName = certificateName;
    }

    public byte[] getCsr() {
        return csr;
    }

    public void setCsr(byte[] csr) {
        this.csr = csr;
    }

    public String getValidFrom() {
        return validFrom;
    }

    public void setValidFrom(String validFrom) {
        this.validFrom = validFrom;
    }

    public CertificateType getCertificateType() {
        return certificateType;
    }

    public void setCertificateType(CertificateType certificateType) {
        this.certificateType = certificateType;
    }
}


package pl.akmf.ksef.sdk.client.model.certificate;

public class CertificateLimitsResponse {
    private Boolean canRequest;
    private CertificateLimit enrollment;
    private CertificateLimit certificate;

    public CertificateLimitsResponse() {
    }

    public Boolean getCanRequest() {
        return canRequest;
    }

    public void setCanRequest(Boolean canRequest) {
        this.canRequest = canRequest;
    }

    public CertificateLimit getEnrollment() {
        return enrollment;
    }

    public void setEnrollment(CertificateLimit enrollment) {
        this.enrollment = enrollment;
    }

    public CertificateLimit getCertificate() {
        return certificate;
    }

    public void setCertificate(CertificateLimit certificate) {
        this.certificate = certificate;
    }
}


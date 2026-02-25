package pl.akmf.ksef.sdk.client.model.certificate;

public class CertificateRevokeRequest {
    private CertificateRevocationReason revocationReason;

    public CertificateRevokeRequest() {
    }

    public CertificateRevokeRequest(CertificateRevocationReason revocationReason) {
        this.revocationReason = revocationReason;
    }

    public CertificateRevocationReason getRevocationReason() {
        return revocationReason;
    }

    public void setRevocationReason(CertificateRevocationReason revocationReason) {
        this.revocationReason = revocationReason;
    }
}


package pl.akmf.ksef.sdk.api.builders.certificate;

import pl.akmf.ksef.sdk.client.model.certificate.CertificateRevocationReason;
import pl.akmf.ksef.sdk.client.model.certificate.CertificateRevokeRequest;

public class CertificateRevokeRequestBuilder {
    private CertificateRevocationReason revocationReason;

    public CertificateRevokeRequestBuilder withRevocationReason(final CertificateRevocationReason revocationReason) {
        this.revocationReason = revocationReason;
        return this;
    }

    public CertificateRevokeRequest build() {
        CertificateRevokeRequest revokeCertificateRequest = new CertificateRevokeRequest();
        revokeCertificateRequest.setRevocationReason(revocationReason);
        return revokeCertificateRequest;
    }
}

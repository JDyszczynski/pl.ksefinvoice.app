package pl.akmf.ksef.sdk.api.builders.certificate;

import pl.akmf.ksef.sdk.client.model.certificate.CertificateType;
import pl.akmf.ksef.sdk.client.model.certificate.SendCertificateEnrollmentRequest;

public class SendCertificateEnrollmentRequestBuilder {
    private String certificateName;
    private byte[] csr;
    private String validFrom;
    private CertificateType certificateType;

    public SendCertificateEnrollmentRequestBuilder withCertificateName(String certificateName) {
        this.certificateName = certificateName;
        return this;
    }

    public SendCertificateEnrollmentRequestBuilder withCsr(byte[] csr) {
        this.csr = csr;
        return this;
    }

    public SendCertificateEnrollmentRequestBuilder withValidFrom(String validFrom) {
        this.validFrom = validFrom;
        return this;
    }

    public SendCertificateEnrollmentRequestBuilder withCertificateType(CertificateType certificateType) {
        this.certificateType = certificateType;
        return this;
    }

    public SendCertificateEnrollmentRequest build() {
        SendCertificateEnrollmentRequest request = new SendCertificateEnrollmentRequest();
        request.setCertificateName(certificateName);
        request.setCsr(csr);
        request.setValidFrom(validFrom);
        request.setCertificateType(certificateType);

        return request;
    }
}

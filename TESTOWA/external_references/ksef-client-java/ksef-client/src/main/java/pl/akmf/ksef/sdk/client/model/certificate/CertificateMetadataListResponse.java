package pl.akmf.ksef.sdk.client.model.certificate;

import java.util.List;

public class CertificateMetadataListResponse {
    private List<CertificateInfo> certificates;
    private Boolean hasMore;

    public CertificateMetadataListResponse() {
    }

    public CertificateMetadataListResponse(List<CertificateInfo> certificates, Boolean hasMore) {
        this.certificates = certificates;
        this.hasMore = hasMore;
    }

    public List<CertificateInfo> getCertificates() {
        return certificates;
    }

    public void setCertificates(List<CertificateInfo> certificates) {
        this.certificates = certificates;
    }

    public Boolean getHasMore() {
        return hasMore;
    }

    public void setHasMore(Boolean hasMore) {
        this.hasMore = hasMore;
    }
}


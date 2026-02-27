package pl.akmf.ksef.sdk.client.model.certificate;

public class CertificateLimit {
    private Integer remaining;
    private Integer limit;

    public CertificateLimit() {
    }

    public CertificateLimit(Integer remaining, Integer limit) {
        this.remaining = remaining;
        this.limit = limit;
    }

    public Integer getRemaining() {
        return remaining;
    }

    public void setRemaining(Integer remaining) {
        this.remaining = remaining;
    }

    public Integer getLimit() {
        return limit;
    }

    public void setLimit(Integer limit) {
        this.limit = limit;
    }
}


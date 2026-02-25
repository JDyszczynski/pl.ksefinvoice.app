package pl.akmf.ksef.sdk.client.model.session.online;

public class SendInvoiceResponse {
    private String referenceNumber;

    public SendInvoiceResponse() {
    }

    public SendInvoiceResponse(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public void setReferenceNumber(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }
}


package pl.akmf.ksef.sdk.client.model.session.batch;

import java.util.ArrayList;
import java.util.List;

public class OpenBatchSessionResponse {
    private String referenceNumber;
    private List<PackagePartSignatureInitResponseType> partUploadRequests;

    public OpenBatchSessionResponse() {
    }

    public OpenBatchSessionResponse(String referenceNumber, List<PackagePartSignatureInitResponseType> partUploadRequests) {
        this.referenceNumber = referenceNumber;
        this.partUploadRequests = partUploadRequests;
    }

    public String getReferenceNumber() {
        return referenceNumber;
    }

    public void setReferenceNumber(String referenceNumber) {
        this.referenceNumber = referenceNumber;
    }

    public List<PackagePartSignatureInitResponseType> getPartUploadRequests() {
        return partUploadRequests;
    }

    public void setPartUploadRequests(List<PackagePartSignatureInitResponseType> partUploadRequests) {
        this.partUploadRequests = partUploadRequests;
    }

    public void addPartUploadRequests(PackagePartSignatureInitResponseType partUploadRequest) {
        if (this.partUploadRequests == null) {
            this.partUploadRequests = new ArrayList<>();
        }
        this.partUploadRequests.add(partUploadRequest);
    }
}

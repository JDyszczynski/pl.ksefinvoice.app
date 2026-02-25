package pl.akmf.ksef.sdk.client.model.session.batch;

import java.util.List;

public class BatchFileInfo {
    private long fileSize;
    private String fileHash;
    private List<BatchFilePartInfo> fileParts;

    public BatchFileInfo() {

    }

    public BatchFileInfo(long fileSize, String fileHash, List<BatchFilePartInfo> fileParts) {
        this.fileSize = fileSize;
        this.fileHash = fileHash;
        this.fileParts = fileParts;
    }

    public long getFileSize() {
        return fileSize;
    }

    public void setFileSize(long fileSize) {
        this.fileSize = fileSize;
    }

    public String getFileHash() {
        return fileHash;
    }

    public void setFileHash(String fileHash) {
        this.fileHash = fileHash;
    }

    public List<BatchFilePartInfo> getFileParts() {
        return fileParts;
    }

    public void setFileParts(List<BatchFilePartInfo> fileParts) {
        this.fileParts = fileParts;
    }
}

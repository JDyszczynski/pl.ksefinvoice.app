package pl.akmf.ksef.sdk.client.model.session.batch;

import pl.akmf.ksef.sdk.client.model.session.FileMetadata;

import java.io.InputStream;

public class BatchPartStreamSendingInfo {
    private InputStream dataStream;
    private FileMetadata metadata;
    private int ordinalNumber;

    public BatchPartStreamSendingInfo() {
    }

    public BatchPartStreamSendingInfo(InputStream dataStream, FileMetadata metadata, int ordinalNumber) {
        this.dataStream = dataStream;
        this.metadata = metadata;
        this.ordinalNumber = ordinalNumber;
    }

    public InputStream getDataStream() {
        return dataStream;
    }

    public void setDataStream(InputStream dataStream) {
        this.dataStream = dataStream;
    }

    public FileMetadata getMetadata() {
        return metadata;
    }

    public void setMetadata(FileMetadata metadata) {
        this.metadata = metadata;
    }

    public int getOrdinalNumber() {
        return ordinalNumber;
    }

    public void setOrdinalNumber(int ordinalNumber) {
        this.ordinalNumber = ordinalNumber;
    }

}

package pl.akmf.ksef.sdk.client.model.session;

import java.util.List;

public class UpoResponse {
    private List<UpoPageResponse> pages;

    public UpoResponse() {
    }

    public UpoResponse(List<UpoPageResponse> pages) {
        this.pages = pages;
    }

    public List<UpoPageResponse> getPages() {
        return pages;
    }

    public void setPages(List<UpoPageResponse> pages) {
        this.pages = pages;
    }
}


package pl.akmf.ksef.sdk.client.model.auth;

import java.util.List;

public class QueryTokensResponse {
  private String continuationToken;
  private List<AuthenticationToken> tokens;

  public QueryTokensResponse() { 
  }

  public String getContinuationToken() {
    return continuationToken;
  }

  public void setContinuationToken(String continuationToken) {
    this.continuationToken = continuationToken;
  }

  public List<AuthenticationToken> getTokens() {
    return tokens;
  }

  public void setTokens(List<AuthenticationToken> tokens) {
    this.tokens = tokens;
  }
}

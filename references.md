```text
●                     ┌──────────────────────────────────────────────────────────┐
                      │  Local PC (Windows)                                      │
                      │  ┌────────────────────────────────────────────────────┐  │
                      │  │  python api_test.py                                │  │
                      │  │   ├─ cognito_test.sign_in()                        │  │
                      │  │   └─ urllib POST                                   │  │
                      │  └────────────────────────────────────────────────────┘  │
                      └────────────┬─────────────────────────────┬───────────────┘
                                   │                             │
                         ① InitiateAuth                    ④ POST /ses/send-email
                            USER_PASSWORD_AUTH                 Authorization:
                            + SECRET_HASH                        Bearer <IdToken>
                                   │                             │
                                   ▼                             ▼
          ┌─────────────────────────────────────┐   ┌────────────────────────────────────┐
          │ Amazon Cognito (us-east-1)          │   │ API Gateway (us-east-1)            │
          │ User Pool:                          │   │ p3rsk2qqqqq.execute-api...         │
          │  ─ Verify password                  │   │ Stage: /production                 │
          │  ─ Issue JWT (RS256, 1h)            │   │ Route: POST /ses/send-email        │
          └─────────────────────────────────────┘   └────────┬───────────────────────────┘
                                   │                         │
                          ② tokens │                         │ ⑤ Validate JWT
                             Access│                         │   (Cognito Authorizer)
                             Id    │                         │   ─ fetch JWKS from
                             Refresh                         │     Cognito /jwks.json
                                   │                         │   ─ verify RS256 sig
                                   ▼                         │   ─ check iss / aud / exp
                      ┌────────────────────────┐             ▼
                      │ Local PC               │   ┌────────────────────────────────────┐
                      │ tokens in memory       │   │ AWS Lambda (us-east-1)             │
                      └────────────────────────┘   │ Handler: sesSendEmail              │
                                   │               │  ─ Parse {to, subject, message}    │
                               ③ pick IdToken      │  ─ boto3 SES client                │
                                   │               │      region = us-east-1       │
                                   └─────────────► └────────┬───────────────────────────┘
                                                            │
                                                  ⑥ SendEmail (cross-region call)
                                                            │
                                                            ▼
                                         ┌────────────────────────────────────┐
                                         │ Amazon SES (us-east-1)             │
                                         │  ─ Verified identity check         │
                                         │     ✓ moonju.khim@gmail.com        │
                                         │  ─ Deliver to recipient mailbox    │
                                         └────────┬───────────────────────────┘
                                                  │
                                         ⑦ MessageId
                                                  │
                                                  ▼
                                         ┌────────────────────────────────────┐
                                         │ 200 OK                             │
                                         │ {"message":"Email sent ...",       │
                                         │  "messageId":"010001...000000"}    │
                                         └────────┬───────────────────────────┘
                                                  │
                                         ⑧ HTTP response back through API GW
                                                  │
                                                  ▼
                                    ┌──────────────────────────────────┐
                                    │ Local PC: print status/headers/  │
                                    │ body in terminal                 │
                                    └──────────────────────────────────┘

  단계 요약
  1. initiate_auth (USER_PASSWORD_AUTH + SECRET_HASH) → Cognito
  2. Access / Id / Refresh 토큰 수신 (RS256, 1시간 유효)
  3. IdToken 선택 (Cognito Authorizer 기본값)
  4. POST /production/ses/send-email + Authorization: Bearer <IdToken>
  5. API Gateway의 Cognito Authorizer가 JWKS로 서명·iss·aud·exp 검증
  6. Lambda → boto3 SES 클라이언트(ap-northeast-2)로 SendEmail
  7. SES verified identity 통과 → 메일 발송 → MessageId 리턴
  8. 200 OK가 Lambda → API Gateway → 클라이언트로 전파
```

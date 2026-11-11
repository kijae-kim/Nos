// 최소 서비스 워커: 홈 화면 설치용. 푸시 알림과 오프라인 캐시는 이후 단계에서 추가한다.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

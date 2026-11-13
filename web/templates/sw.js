// 서비스 워커: 홈 화면 설치와 기념일 알림(웹 푸시). 오프라인 캐시는 하지 않는다.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// 서버(notifications/push.py)가 보낸 알림을 띄운다. 내용: {title, body, url, tag}
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : "" };
  }
  const icon = "/static/icons/icon-192.png";
  event.waitUntil(
    self.registration.showNotification(data.title || "NÓS", {
      body: data.body || "",
      tag: data.tag,
      icon,
      badge: icon,
      data: { url: data.url || "/" },
    })
  );
});

// 알림을 누르면 열린 앱 창으로 가고, 없으면 새로 연다.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const win of windows) {
        if (new URL(win.url).origin === self.location.origin && "focus" in win) {
          return win.focus().then((w) => (w && "navigate" in w ? w.navigate(url) : w));
        }
      }
      return self.clients.openWindow(url);
    })
  );
});

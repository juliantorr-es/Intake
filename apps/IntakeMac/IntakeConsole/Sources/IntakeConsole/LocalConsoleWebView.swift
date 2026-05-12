import SwiftUI
import WebKit

struct LocalConsoleWebView: NSViewRepresentable {
    let url: URL
    let reloadTrigger: Int
    
    func makeNSView(context: Context) -> WKWebView {
        let userScript = WKUserScript(source: "document.body.classList.add('native-shell');", injectionTime: .atDocumentEnd, forMainFrameOnly: true)
        let contentController = WKUserContentController()
        contentController.addUserScript(userScript)
        
        let configuration = WKWebViewConfiguration()
        configuration.userContentController = contentController
        
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        
        let request = URLRequest(url: url)
        webView.load(request)
        
        return webView
    }
    
    func updateNSView(_ nsView: WKWebView, context: Context) {
        if nsView.url == nil {
            let request = URLRequest(url: url)
            nsView.load(request)
        } else if context.coordinator.lastReloadTrigger != reloadTrigger {
            nsView.reload()
            context.coordinator.lastReloadTrigger = reloadTrigger
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }
    
    class Coordinator: NSObject, WKNavigationDelegate {
        var parent: LocalConsoleWebView
        var lastReloadTrigger: Int = 0
        
        init(_ parent: LocalConsoleWebView) {
            self.parent = parent
        }
        
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }
            
            // Strict loopback restriction
            let host = url.host ?? ""
            if host == "127.0.0.1" || host == "localhost" {
                decisionHandler(.allow)
            } else {
                print("Navigation blocked to external URL: \(url)")
                decisionHandler(.cancel)
            }
        }
    }
}

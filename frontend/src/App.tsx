import { brand, safeHref } from "./brand";
import { ChatWindow } from "./components/ChatWindow";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";

/** `?embed=1` renders only the chat panel, for embedding in an iframe on the official site. */
export function isEmbedMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("embed") === "1";
}

export default function App() {
  if (isEmbedMode()) {
    return (
      <main className="embed">
        <ChatWindow />
      </main>
    );
  }

  return (
    <>
      <a className="skip-link" href="#chat-message">
        Skip to the question box
      </a>
      <Header />
      <div className="page-banner">
        <div className="container">
          <h1 className="page-banner__title">Virtual Assistant</h1>
          <nav aria-label="Breadcrumb">
            <ol className="breadcrumb">
              <li>
                <a href={safeHref(brand.official_url)}>Home</a>
              </li>
              <li aria-current="page">Virtual Assistant</li>
            </ol>
          </nav>
        </div>
      </div>
      <main className="container page-main">
        <ChatWindow />
      </main>
      <Footer />
    </>
  );
}

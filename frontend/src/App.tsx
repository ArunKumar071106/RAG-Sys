import { useEffect, useState } from "react";
import { brand, safeHref } from "./brand";
import { DEFAULT_SUGGESTIONS } from "./components/SuggestedQuestions";
import { ChatWidget } from "./components/ChatWidget";
import { ChatWindow } from "./components/ChatWindow";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";

/** `?embed=1` renders only the chat panel, for embedding in an iframe on the official site. */
export function isEmbedMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("embed") === "1";
}

/** `?widget=1` renders only the floating launcher and panel, for public/arivazhai-widget.js on the official site. */
export function isWidgetMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("widget") === "1";
}

function WidgetOnly() {
  useEffect(() => {
    document.documentElement.classList.add("is-widget-frame"); // transparent page behind the launcher
    return () => document.documentElement.classList.remove("is-widget-frame");
  }, []);
  return <ChatWidget widget />;
}

export default function App() {
  const [chatOpen, setChatOpen] = useState(false);

  if (isWidgetMode()) return <WidgetOnly />;

  if (isEmbedMode()) {
    return (
      <main className="embed">
        <ChatWindow />
      </main>
    );
  }

  return (
    <>
      <a
        className="skip-link"
        href="#arivazhai-panel"
        onClick={(event) => {
          event.preventDefault();
          setChatOpen(true);
        }}
      >
        Skip to the assistant
      </a>
      <Header />
      <div
        className={`page-banner${brand.banner_image ? " page-banner--image" : ""}`}
        style={brand.banner_image ? { backgroundImage: `url("${brand.banner_image}")` } : undefined}
      >
        <div className="container">
          <div className="page-banner__box">
            <h1 className="page-banner__title">Virtual Assistant</h1>
            <p className="page-banner__lead">Ask about admissions, departments, placements and campus life - answered from the official website.</p>
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
      </div>
      <main className="container page-main">
        <section className="intro" aria-labelledby="intro-title">
          <h2 id="intro-title" className="intro__title">
            Meet Arivazhai, the {brand.short_name} admission assistant
          </h2>
          <p className="intro__lead">
            Arivazhai answers questions about {brand.college_name} from the official website, with a link to every source. It
            waits in the bottom-right corner of the page: open it any time.
          </p>
          <button type="button" className="btn btn--primary" onClick={() => setChatOpen(true)} aria-controls="arivazhai-panel">
            Ask Arivazhai
          </button>
          <h3 className="intro__subtitle">Questions you can ask</h3>
          <ul className="intro__list">
            {DEFAULT_SUGGESTIONS.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </section>
      </main>
      <Footer />
      <ChatWidget open={chatOpen} onOpenChange={setChatOpen} />
    </>
  );
}

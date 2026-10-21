import { brand, safeHref } from "./brand";
import { ChatWindow, startChat } from "./components/ChatWindow";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { RobotMoments } from "./robot/RobotMoments";

/** `?embed=1` renders only the chat panel, for embedding in an iframe on the official site. */
export function isEmbedMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get("embed") === "1";
}

export default function App() {
  if (isEmbedMode()) {
    return (
      <main className="embed">
        <ChatWindow />
        <RobotMoments />
      </main>
    );
  }

  return (
    <>
      <a className="skip-link" href="#chat-message">
        Skip to the question box
      </a>
      <Header />
      <div
        className={`page-banner${brand.banner_image ? " page-banner--image" : ""}`}
        style={brand.banner_image ? { backgroundImage: `url("${brand.banner_image}")` } : undefined}
      >
        <div className="container">
          <div className="page-banner__box">
            <h1 className="page-banner__title">Arivazhai</h1>
            <p className="page-banner__lead">Ask about admissions, departments, placements and campus life - answered from the official website.</p>
            <button type="button" className="btn btn--start" onClick={startChat}>
              <span aria-hidden="true">💬</span> Start chat with Arivazhai
            </button>
            <nav aria-label="Breadcrumb">
              <ol className="breadcrumb">
                <li>
                  <a href={safeHref(brand.official_url)}>Home</a>
                </li>
                <li aria-current="page">Arivazhai</li>
              </ol>
            </nav>
          </div>
        </div>
      </div>
      <main className="container page-main">
        <ChatWindow />
      </main>
      <Footer />
      <RobotMoments />
    </>
  );
}

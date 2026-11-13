/*
 * The chat's words in English and Tamil. The "தமிழ் / English" button in the chat header switches
 * them (remembered in this browser). Answers follow the language of the question: with the AI
 * model, a question in Tamil is answered in Tamil. The college's header, menu and footer stay as
 * the official website writes them.
 *
 * In index.html, data-i18n="key" sets an element's text and data-i18n-attr="placeholder:key" an
 * attribute; the scripts call Arivazhai.i18n.t("key").
 */
(function (A) {
  "use strict";

  const phone = (A.site && A.site.officePhones[0]) || "";

  const STRINGS = {
    en: {
      switchTo: "தமிழ்",
      switchLabel: "Show the chat in Tamil",
      subtitle: "AAACET admission help desk · answers from the official website",
      newChat: "New chat",
      welcome:
        "Vanakkam! I'm Arivazhai, the AAACET admission assistant. Ask me about eligibility, TNEA counselling, courses, fees, " +
        "scholarships, hostel or placements. I answer from the official website and link every source.",
      tryAsking: "Try asking",
      preset1: "What is the eligibility for B.E. / B.Tech admission?",
      preset2: "What is the TNEA counselling code of AAACET?",
      preset3: "How many seats are there in each department?",
      preset4: "How do I apply for admission online?",
      preset5: "What documents are needed for admission?",
      preset6: "What scholarships are available based on +2 cut-off marks?",
      preset7: "Are hostels available for boys and girls?",
      preset8: "Whom should I contact for admission?",
      placeholder: "Ask about admissions, courses, facilities…",
      hint: "Press Enter to send, Shift + Enter for a new line. Use ↑ ↓ to pick a suggestion.",
      send: "Send",
      sendLabel: "Send message",
      mic: "Ask by voice",
      micStop: "Stop listening",
      listening: "Listening… speak now",
      micDenied: "Microphone access was blocked. Allow it in the browser's address bar to ask by voice.",
      micFailed: "Could not hear that. Please try again or type your question.",
      searching: "Searching the official website…",
      sources: "Sources from the official website",
      related: "These official pages may be related",
      images: "Images from the official website",
      alsoAsk: "You can also ask",
      helpful: "Was this answer helpful?",
      yes: "Yes, helpful",
      no: "No, not helpful",
      whatWrong: "What was wrong or missing? (optional)",
      sendFeedback: "Send",
      thanks: "Thank you! Your feedback helps us improve the answers.",
      talk: "Need to talk to someone?",
      call: "Call the admission office",
      email: "Email",
      whatsapp: "WhatsApp",
      contactCollege: "Contact the college",
      officeHelps: "The admission office can help you directly",
      staffTitle: "Admission & scholarship",
      tollFree: "(toll-free)",
      tryAgain: "Try again",
      chatBelow: "Chat below",
      showEnglish: "Show in English",
      showOriginal: "Show original",
      translating: "Translating…",
      err_network: "Can't reach the assistant right now. Please check your connection and try again.",
      err_timeout: "The assistant took too long to respond. Please try again.",
      err_rate_limited: "You're sending messages too quickly. Please wait a moment and try again.",
      err_starting: "The assistant is still starting up. Please try again in a minute.",
      err_unavailable: "The assistant is temporarily unavailable. Please try again later.",
      err_server: "Something went wrong on our side. Please try again.",
      m_greet_title: "Vanakkam! I'm Arivazhai",
      m_greet_text: "Your guide to AAACET admissions. Ask me anything.",
      m_load_title: "Getting ready…",
      m_load_text: "Loading the official AAACET website content.",
      m_think_title: "Finding your answer…",
      m_think_text: "Searching the official AAACET website.",
      m_error_title: "Something went wrong",
      m_error_text: "Please try again in a moment.",
      m_net_title: "You're offline",
      m_net_text: "Check your connection and try again.",
      m_network_title: "Can't reach the assistant",
      m_network_text: "Please check your connection and try again.",
      m_timeout_title: "That took too long",
      m_rate_title: "Too many questions at once",
      m_rate_text: "Please wait a moment and try again.",
      m_starting_title: "Still getting ready",
      m_starting_text: "Please try again in a minute.",
      m_rephrase_title: "Could you rephrase that?",
      m_rephrase_text: "Ask about admissions, courses, fees or campus life.",
      m_unsure_title: "I couldn't find that",
      m_unsure_text: phone ? "Call the admission office: " + phone : "The admission office can help you directly.",
    },
    ta: {
      switchTo: "English",
      switchLabel: "Show the chat in English",
      subtitle: "AAACET சேர்க்கை உதவி மையம் · அதிகாரப்பூர்வ இணையதளத்திலிருந்து பதில்கள்",
      newChat: "புதிய உரையாடல்",
      welcome:
        "வணக்கம்! நான் Arivazhai, AAACET சேர்க்கை உதவியாளர். தகுதி, TNEA கலந்தாய்வு, படிப்புகள், கட்டணம், உதவித்தொகை, " +
        "விடுதி அல்லது வேலைவாய்ப்பு பற்றி என்னிடம் கேளுங்கள். அதிகாரப்பூர்வ இணையதளத்திலிருந்து பதில் தருவேன், ஒவ்வொரு " +
        "தகவலுக்கும் இணைப்பும் தருவேன்.",
      tryAsking: "இவற்றைக் கேட்டுப் பாருங்கள்",
      preset1: "B.E. / B.Tech சேர்க்கைக்கான தகுதி என்ன?",
      preset2: "AAACET-இன் TNEA கலந்தாய்வுக் குறியீடு என்ன?",
      preset3: "ஒவ்வொரு துறையிலும் எத்தனை இடங்கள் உள்ளன?",
      preset4: "ஆன்லைனில் சேர்க்கைக்கு எப்படி விண்ணப்பிப்பது?",
      preset5: "சேர்க்கைக்குத் தேவையான ஆவணங்கள் என்ன?",
      preset6: "+2 கட்-ஆஃப் மதிப்பெண் அடிப்படையில் என்ன உதவித்தொகைகள் உள்ளன?",
      preset7: "ஆண்கள் மற்றும் பெண்களுக்கு விடுதி வசதி உள்ளதா?",
      preset8: "சேர்க்கைக்கு யாரைத் தொடர்பு கொள்ள வேண்டும்?",
      placeholder: "சேர்க்கை, படிப்புகள், வசதிகள் பற்றிக் கேளுங்கள்…",
      hint: "அனுப்ப Enter, புதிய வரிக்கு Shift + Enter. பரிந்துரையைத் தேர்ந்தெடுக்க ↑ ↓.",
      send: "அனுப்பு",
      sendLabel: "செய்தியை அனுப்பு",
      mic: "குரலில் கேளுங்கள்",
      micStop: "கேட்பதை நிறுத்து",
      listening: "கேட்கிறது… இப்போது பேசுங்கள்",
      micDenied: "மைக்ரோஃபோன் அனுமதி தடுக்கப்பட்டுள்ளது. குரலில் கேட்க, உலாவியின் முகவரிப் பட்டியில் அனுமதியுங்கள்.",
      micFailed: "சரியாகக் கேட்கவில்லை. மீண்டும் முயற்சிக்கவும் அல்லது கேள்வியைத் தட்டச்சு செய்யவும்.",
      searching: "அதிகாரப்பூர்வ இணையதளத்தில் தேடுகிறது…",
      sources: "அதிகாரப்பூர்வ இணையதள ஆதாரங்கள்",
      related: "தொடர்புடைய அதிகாரப்பூர்வ பக்கங்கள்",
      images: "அதிகாரப்பூர்வ இணையதளப் படங்கள்",
      alsoAsk: "இதையும் கேட்கலாம்",
      helpful: "இந்தப் பதில் உதவியாக இருந்ததா?",
      yes: "ஆம், உதவியது",
      no: "இல்லை, உதவவில்லை",
      whatWrong: "என்ன தவறு அல்லது எது இல்லை? (விருப்பம்)",
      sendFeedback: "அனுப்பு",
      thanks: "நன்றி! உங்கள் கருத்து பதில்களை மேம்படுத்த உதவும்.",
      talk: "நேரடியாகப் பேச வேண்டுமா?",
      call: "சேர்க்கை அலுவலகத்தை அழைக்க",
      email: "மின்னஞ்சல்",
      whatsapp: "வாட்ஸ்அப்",
      contactCollege: "கல்லூரியைத் தொடர்பு கொள்ள",
      officeHelps: "சேர்க்கை அலுவலகம் நேரடியாக உதவும்",
      staffTitle: "சேர்க்கை & உதவித்தொகை",
      tollFree: "(கட்டணமில்லா எண்)",
      tryAgain: "மீண்டும் முயற்சி",
      chatBelow: "கீழே உரையாடல்",
      showEnglish: "ஆங்கிலத்தில் காட்டு",
      showOriginal: "மூலத்தைக் காட்டு",
      translating: "மொழிபெயர்க்கிறது…",
      err_network: "இப்போது உதவியாளரை அணுக முடியவில்லை. இணைப்பைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்.",
      err_timeout: "பதில் வர நீண்ட நேரம் ஆனது. மீண்டும் முயற்சிக்கவும்.",
      err_rate_limited: "மிக வேகமாகக் கேள்விகள் அனுப்புகிறீர்கள். சிறிது நேரம் கழித்து முயற்சிக்கவும்.",
      err_starting: "உதவியாளர் இன்னும் தயாராகிறது. ஒரு நிமிடம் கழித்து முயற்சிக்கவும்.",
      err_unavailable: "உதவியாளர் தற்காலிகமாகக் கிடைக்கவில்லை. பிறகு முயற்சிக்கவும்.",
      err_server: "எங்கள் பக்கத்தில் ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்.",
      m_greet_title: "வணக்கம்! நான் Arivazhai",
      m_greet_text: "AAACET சேர்க்கைக்கான உங்கள் வழிகாட்டி. எதையும் கேளுங்கள்.",
      m_load_title: "தயாராகிறது…",
      m_load_text: "அதிகாரப்பூர்வ AAACET இணையதளத் தகவல்களை ஏற்றுகிறது.",
      m_think_title: "பதிலைத் தேடுகிறது…",
      m_think_text: "அதிகாரப்பூர்வ AAACET இணையதளத்தில் தேடுகிறது.",
      m_error_title: "ஏதோ தவறு நடந்தது",
      m_error_text: "சிறிது நேரத்தில் மீண்டும் முயற்சிக்கவும்.",
      m_net_title: "இணைய இணைப்பு இல்லை",
      m_net_text: "இணைப்பைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்.",
      m_network_title: "உதவியாளரை அணுக முடியவில்லை",
      m_network_text: "இணைப்பைச் சரிபார்த்து மீண்டும் முயற்சிக்கவும்.",
      m_timeout_title: "அதிக நேரம் ஆனது",
      m_rate_title: "ஒரே நேரத்தில் அதிகக் கேள்விகள்",
      m_rate_text: "சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
      m_starting_title: "இன்னும் தயாராகிறது",
      m_starting_text: "ஒரு நிமிடம் கழித்து முயற்சிக்கவும்.",
      m_rephrase_title: "வேறு விதமாகக் கேட்க முடியுமா?",
      m_rephrase_text: "சேர்க்கை, படிப்புகள், கட்டணம் அல்லது வளாக வாழ்க்கை பற்றிக் கேளுங்கள்.",
      m_unsure_title: "அதைக் கண்டுபிடிக்க முடியவில்லை",
      m_unsure_text: phone ? "சேர்க்கை அலுவலகத்தை அழைக்கவும்: " + phone : "சேர்க்கை அலுவலகம் நேரடியாக உதவும்.",
    },
  };

  const KEY = "arivazhai-lang";
  let lang = "en";
  try {
    if (window.localStorage.getItem(KEY) === "ta") lang = "ta";
  } catch (e) {
    /* storage blocked: English */
  }
  const listeners = [];

  function t(key) {
    return (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;
  }

  /** Put the current language's words into every marked element under root. */
  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    scope.querySelectorAll("[data-i18n-attr]").forEach((node) => {
      node.getAttribute("data-i18n-attr").split(";").forEach((pair) => {
        const [attr, key] = pair.split(":").map((x) => x.trim());
        if (attr && key) node.setAttribute(attr, t(key));
      });
    });
    const chat = document.getElementById("assistant");
    if (chat) chat.setAttribute("lang", lang === "ta" ? "ta" : "en");
  }

  function set(next) {
    lang = next === "ta" ? "ta" : "en";
    try {
      window.localStorage.setItem(KEY, lang);
    } catch (e) {
      /* not remembered: fine */
    }
    apply();
    listeners.forEach((fn) => fn(lang));
  }

  A.i18n = {
    t: t,
    apply: apply,
    set: set,
    toggle: () => set(lang === "ta" ? "en" : "ta"),
    get lang() {
      return lang;
    },
    /** BCP-47 language for speech recognition. */
    get speech() {
      return lang === "ta" ? "ta-IN" : "en-IN";
    },
    onChange: (fn) => listeners.push(fn),
    STRINGS: STRINGS,
  };
})((window.Arivazhai = window.Arivazhai || {}));

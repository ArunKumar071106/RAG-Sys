/*
 * The college's details the chat shows: from the official website's footer and contact page
 * (https://aaaenggcoll.ac.in/contact-us/) and the admission page's "For ADMISSION & SCHOLARSHIP
 * CONTACT" table. Kept by hand.
 */
(function (A) {
  "use strict";

  A.site = {
    collegeName: "AAA College of Engineering and Technology",
    shortName: "AAACET",
    officialUrl: "https://aaaenggcoll.ac.in/",
    officePhones: ["04562-251111", "04562-251112", "18004258807"],
    emails: ["enquiry@aaacet.ac.in", "admissions@aaacet.ac.in"],
    // The admission office's WhatsApp number with the country code, e.g. "917373527252"; empty: no WhatsApp button.
    // Ask the office for the number they answer on WhatsApp before filling it in.
    whatsapp: "",
    admissionStaff: [
      { name: "Dr. N. Thenmoezhi", phone: "9688449326" },
      { name: "Mr. R. Chandhran", role: "Admission officer", phone: "7373527252" },
      { name: "Mr. D. John Elisa", phone: "9003129428" },
      { name: "Dr. P. Senthil Pandian", phone: "9159699366" },
      { name: "Mr. P. Manikandan", phone: "97884 92136" },
    ],
  };
})((window.Arivazhai = window.Arivazhai || {}));

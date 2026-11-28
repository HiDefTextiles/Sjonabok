// Cookie consent for the HiDef Textiles sites (main site, Sjonabok gallery,
// Sjonabok-stafrof), built on Klaro! (klaro.js, BSD-3-Clause, see
// LICENSE-klaro), the same consent manager hi.is uses. Our own wording.
// Keep this file identical in all three repositories.
//
// Site settings come from <meta name="ga-measurement-id"> in _quarto.yml:
//   content             Google Tag Manager container (GTM-...) or GA4 ID (G-...)
//   data-privacy-href   link to the privacy text
//   data-langs          "is" (Icelandic only) or "en is" (browser language picks)
//   data-services       optional extra services, e.g. "youtube"
//
// Categories (as on hi.is):
//   Vefmælingar / Analytics: Google Analytics (via GTM), YouTube if the site
//     embeds videos. Off until the visitor accepts.
//   Útlit / Appearance (required): Google Fonts. Always on.
// Nothing is sent to Google Analytics before consent: gtm.js is only loaded
// from onAccept, with Consent Mode analytics granted and ads denied. YouTube
// iframes carry data-name="youtube" data-src=... (filters/consent-embeds.lua
// on the main site) and show a "load video" notice until accepted.
// The choice is stored in localStorage ("hidef-consent"), shared by all three
// sites on hideftextiles.github.io. Links to #analytics-settings reopen it.
// Pages shown in an iframe never show the notice and never track.
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="ga-measurement-id"]');
  if (!meta) return;
  var id = (meta.getAttribute("content") || "").trim();
  var embedded;
  try { embedded = window.self !== window.top; } catch (e) { embedded = true; }

  var langs = (meta.getAttribute("data-langs") || "en").split(/\s+/);
  var lang = langs[0];
  var nav = (navigator.languages || [navigator.language || ""]).map(function (l) {
    return String(l).slice(0, 2).toLowerCase();
  });
  for (var i = 0; i < nav.length; i++) {
    if (langs.indexOf(nav[i]) >= 0) { lang = nav[i]; break; }
  }
  var extra = (meta.getAttribute("data-services") || "").split(/\s+/);
  var privacy = meta.getAttribute("data-privacy-href") || "";

  function loadAnalytics() {
    if (window.__hidefAnalyticsLoaded || !/^(G|GTM)-[A-Z0-9]+$/.test(id) || /^(G|GTM)-X+$/.test(id)) return;
    window.__hidefAnalyticsLoaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    gtag("consent", "default", {
      analytics_storage: "granted",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied"
    });
    var s = document.createElement("script");
    s.async = true;
    if (id.indexOf("GTM-") === 0) {
      window.dataLayer.push({ "gtm.start": new Date().getTime(), event: "gtm.js" });
      s.src = "https://www.googletagmanager.com/gtm.js?id=" + encodeURIComponent(id);
    } else {
      gtag("js", new Date());
      gtag("config", id);
      s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
    }
    document.head.appendChild(s);
  }

  var services = [
    {
      name: "googleAnalytics",
      title: "Google Analytics",
      purposes: ["analytics"],
      default: false,
      cookies: [/^_ga(_.*)?$/],
      onAccept: function () { if (!embedded) loadAnalytics(); },
      onDecline: function () {
        // gtm.js can't be unloaded; reload so it is gone for the rest of the visit.
        if (window.__hidefAnalyticsLoaded) location.reload();
      }
    }
  ];
  if (extra.indexOf("youtube") >= 0) {
    services.push({
      name: "youtube",
      title: "YouTube",
      purposes: ["analytics"],
      default: false
    });
  }
  services.push({
    name: "googleFonts",
    title: "Google Fonts",
    purposes: ["styling"],
    required: true
  });

  var privacyText = {
    is: { name: "persónuverndarsíðunni", text: "Nánar á {privacyPolicy}." },
    en: { name: "privacy page", text: "More on our {privacyPolicy}." }
  };

  window.klaroConfig = {
    version: 1,
    elementID: "klaro",
    storageMethod: "localStorage",
    storageName: "hidef-consent",
    htmlTexts: false,
    groupByPurpose: true,
    default: false,
    mustConsent: false,
    acceptAll: true,
    hideDeclineAll: false,
    hideLearnMore: false,
    noticeAsModal: false,
    noAutoLoad: embedded,
    lang: lang,
    additionalClass: "hidef-klaro",
    styling: { theme: ["light", "bottom", "wide"] },
    translations: {
      zz: { privacyPolicyUrl: privacy },
      is: {
        privacyPolicy: privacyText.is,
        acceptAll: "Samþykkja allt",
        acceptSelected: "Samþykkja valið",
        decline: "Hafna",
        ok: "Samþykkja allt",
        save: "Vista",
        close: "Loka",
        poweredBy: "Keyrt á Klaro!",
        consentNotice: {
          title: "Vafrakökur",
          description: "Vefurinn vill nota vafrakökur og ytri þjónustur í flokkunum {purposes}. " +
            "Ekkert slíkt er virkjað fyrr en þú samþykkir og þú getur breytt valinu " +
            "hvenær sem er neðst á síðunni.",
          learnMore: "Stillingar",
          changeDescription: "Þjónustum hefur verið breytt síðan þú komst síðast. " +
            "Vinsamlegast veldu aftur.",
          testing: "Prófunarhamur"
        },
        consentModal: {
          title: "Vafrakökur og þjónustur",
          description: "Hér sérðu hvaða þjónustur vefurinn vill nota og getur kveikt eða " +
            "slökkt á þeim. Vefmælingar hjálpa okkur að sjá hvaða efni er lesið. " +
            "Þær eru óvirkar þar til þú leyfir þær."
        },
        contextualConsent: {
          description: "Viltu sýna efni frá {title}? Þá fær {title} upplýsingar um heimsóknina.",
          acceptOnce: "Já",
          acceptAlways: "Alltaf",
          descriptionEmptyStore: "Til að leyfa {title} alltaf þarf að samþykkja það í {link}.",
          modalLinkText: "stillingum fyrir vafrakökur"
        },
        purposeItem: { service: "þjónusta", services: "þjónustur" },
        service: {
          purpose: "Tilgangur",
          purposes: "Tilgangur",
          required: { title: "(nauðsynlegt)", description: "Alltaf virkt" },
          optOut: { title: "(sjálfgefið á)", description: "Virkt nema þú slökkvir á því" },
          disableAll: {
            title: "Kveikja eða slökkva á öllu",
            description: "Kveikir eða slekkur á öllum þjónustum í einu."
          }
        },
        purposes: {
          analytics: {
            title: "Vefmælingar",
            description: "Telja heimsóknir og sýna hvaða síður og myndbönd eru skoðuð."
          },
          styling: {
            title: "Útlit",
            description: "Það sem síðan þarf til að líta rétt út."
          }
        },
        googleAnalytics: { description: "Telur heimsóknir og sýnir hvaða síður eru lesnar" },
        youtube: { title: "YouTube", description: "Myndbönd sem spilast á síðunni, frá YouTube (Google)" },
        googleFonts: { description: "Leturgerðin Jost, sótt frá Google" }
      },
      en: {
        privacyPolicy: privacyText.en,
        acceptAll: "Accept all",
        acceptSelected: "Accept selected",
        decline: "Reject",
        ok: "Accept all",
        save: "Save",
        close: "Close",
        poweredBy: "Runs on Klaro!",
        consentNotice: {
          title: "Cookies",
          description: "This site would like to use cookies and outside services for {purposes}. " +
            "None of them starts until you agree, and you can change your choice " +
            "any time from the page footer.",
          learnMore: "Let me choose",
          changeDescription: "The services have changed since your last visit. Please choose again.",
          testing: "Testing mode"
        },
        consentModal: {
          title: "Cookies and services",
          description: "Here you can see which services the site would like to use and switch " +
            "them on or off. Analytics shows us which pages are read. It stays off until " +
            "you allow it."
        },
        contextualConsent: {
          description: "Show content from {title}? {title} will then learn about your visit.",
          acceptOnce: "Yes",
          acceptAlways: "Always",
          descriptionEmptyStore: "To always allow {title}, accept it in the {link}.",
          modalLinkText: "cookie settings"
        },
        purposeItem: { service: "service", services: "services" },
        service: {
          purpose: "Purpose",
          purposes: "Purposes",
          required: { title: "(required)", description: "Always on" },
          optOut: { title: "(on by default)", description: "On unless you switch it off" },
          disableAll: {
            title: "Switch everything on or off",
            description: "Switches all services on or off at once."
          }
        },
        purposes: {
          analytics: {
            title: "Analytics",
            description: "Counting visits and seeing which pages and videos are viewed."
          },
          styling: {
            title: "Appearance",
            description: "What the page needs to look right."
          }
        },
        googleAnalytics: { description: "Counts visits and shows which pages are read" },
        youtube: { title: "YouTube", description: "Videos played on the page, from YouTube (Google)" },
        googleFonts: { description: "The Jost typeface, loaded from Google" }
      }
    },
    services: services
  };

  // Footer link: reopen the settings.
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[href$='#analytics-settings']");
    // The bundle registers as window["klaro-no-translations"] (window.klaro is
    // the #klaro element).
    var k = window["klaro-no-translations"];
    if (a && k) { ev.preventDefault(); k.show(undefined, true); }
  });
  if (!embedded) document.documentElement.classList.add("has-analytics");
})();

// Analytics

var ANALYTICS_COOKIE_NAME = 'hasConsentForAnalytics';
var ANALYTICS_COOKIE_TIMEOUT = 33696000000;
var ANALYTICS_DECLINE_COOKIE_NAME = 'hasNoConsentForAnalytics';

// Analytics
function addAnalyticsCookie() {
  if (!checkAnalyticsCookie()) {
    var date = new Date();
    date.setTime(date.getTime() + ANALYTICS_COOKIE_TIMEOUT);
    document.cookie =
      ANALYTICS_COOKIE_NAME + '=true;expires=' + date.toGMTString() + '; Secure; path=/';
  }
}

$(document).on('click', '.rich-text a', function () {
  var URL = $(this).attr('href');
  if (URL.startsWith('/')) {
    window.location.href = window.location.origin+URL;
  }
});

// Analytics
function setAnalyticsDeclineCookie() {
  var date = new Date();
  date.setTime(date.getTime() + ANALYTICS_COOKIE_TIMEOUT);
  document.cookie =
    ANALYTICS_DECLINE_COOKIE_NAME + '=true;expires=' + date.toGMTString() + '; Secure; path=/';
}

// Analytics
function removeAnalyticsCookie() {
  document.cookie =
    ANALYTICS_COOKIE_NAME + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; Secure; path=/;';
}

// Analytics
function removeAnalyticsDeclineCookie() {
  document.cookie =
    ANALYTICS_DECLINE_COOKIE_NAME + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; Secure; path=/;';
}

// Analytics
var attachDemandBaseInBody = function () {
  dbt();
  dbs();
};

// Analytics
function checkAnalyticsCookie() {
  if (document.cookie.indexOf(ANALYTICS_COOKIE_NAME + '=true') > -1) {
    return true;
  } else {
    return false;
  }
}

// Analytics
function checkAnalyticsDeclineCookie() {
  if (document.cookie.indexOf(ANALYTICS_DECLINE_COOKIE_NAME + '=true') > -1) {
    return true;
  } else {
    return false;
  }
}

// Analytics
function dbt() {
  if (document.querySelector('html').classList.contains('dbtriggered')) return;
  (function (d, b, a, s, e) {
    var t = b.createElement(a),
      fs = b.getElementsByTagName(a)[0];
    t.async = 1;
    t.id = e;
    t.src = s;
    fs.parentNode.insertBefore(t, fs);
  })(window, document, 'script', 'https://tag.demandbase.com/FDwiyD6L.min.js', 'demandbase_js_lib');
  document.querySelector('html').classList.add('dbtriggered');
}

function dbs() {
  if (window['Demandbase'] && Demandbase['IP'] && Demandbase.IP['CompanyProfile']) {
    var getData = function (e) {
      var currentContactId = e.id;
      if (!sessionStorage.getItem('getNewDemandBaseData')) {
        jQuery.ajax('/api/kroll/demandbase/getdata', {
          type: 'POST',
          data: {
            currentContact: currentContactId,
            data: JSON.stringify(Demandbase.IP.CompanyProfile),
          },
          success: function (data) {
            if (data.toLowerCase() === 'true') {
              sessionStorage.setItem('getNewDemandBaseData', 'getNewDemandBaseDataTriggered');
            }
          },
        });
      } else {
        return;
      }
    };
    // $('#contact-country').each(function(index, item) {
    //     $(item).val(Demandbase.IP.CompanyProfile.registry_country);
    //     $(item).addClass('touched dirty is-valid');
    // })
    // function getCurrent() {
    //   $.ajax('/api/kroll/contact/current', {
    //     success: function (e) {
    //       if (e.id) {
    //         sessionStorage.setItem('current', JSON.stringify(e));
    //         getData(e);
    //       } else {
    //         // getCurrent();
    //       }
    //     },
    //   });
    // }
    if ($('[data-analytics-disabled]').length === 0) {
      var current = ''; // sessionStorage.getItem('current')
      if (current) {
        var currentData = JSON.parse(current);
        if (currentData.id) {
          getData(currentData);
        } else {
          getCurrent();
        }
      } else {
        getCurrent();
      }
    }
  } else {
    setTimeout(dbs, 30);
  }
}

// Analytics
function checkHasConsentForAnalyticsCookie() {
  var result = window['OnetrustActiveGroups'].indexOf('C0002') !== -1;
  if (!result) {
    if (!checkAnalyticsDeclineCookie()) {
      setAnalyticsDeclineCookie();
    }
  }
  return result;
}

function dockCookieBanner() {
  setTimeout(() => {
    if ($('#onetrust-banner-sdk').height()) {
      $('#onetrust-consent-sdk').css({
        'margin-top': parseInt($('#onetrust-banner-sdk').height()),
      });
    } else {
      dockCookieBanner();
    }
  }, 300);
}

function undockCookieBanner() {
  setTimeout(() => {
    $('#onetrust-consent-sdk').css({ 'margin-top': 0 });
  }, 300);
}

if (document.readyState === 'complete') {
  // Analytics
  function isOneTrustInitialised() {
    if (window['OnetrustActiveGroups'] && window['OnetrustActiveGroups'].indexOf('C0001') !== -1) {
      setTimeout(function () {
        if (document.cookie.indexOf('OptanonAlertBoxClosed') === -1) {
          dockCookieBanner();
        }
        if (checkHasConsentForAnalyticsCookie()) {
          attachDemandBaseInBody();
        }
      }, 30);
    } else {
      setTimeout(isOneTrustInitialised, 30);
    }
  }
  isOneTrustInitialised();

  $(document).on('click', '#onetrust-reject-all-handler', function () {
    // Analytics
    setAnalyticsDeclineCookie();
  });

  $(document).on(
    'click',
    '#onetrust-accept-btn-handler, #accept-recommended-btn-handler, .save-preference-btn-handler',
    function () {
      // Analytics
      if (checkHasConsentForAnalyticsCookie()) {
        if (checkAnalyticsDeclineCookie()) {
          removeAnalyticsDeclineCookie();
        }
        addAnalyticsCookie();
        attachDemandBaseInBody();
      } else {
        if (checkAnalyticsCookie()) {
          removeAnalyticsCookie();
        }
      }
    }
  );
}

$(document).on(
  'click',
  '#onetrust-accept-btn-handler, #onetrust-reject-all-handler, #accept-recommended-btn-handler, .save-preference-btn-handler',
  function () {
    // Analytics
    setTimeout(() => {
      location.reload();
    }, 300);
  }
);

$(document).on('click', '#onetrust-close-btn-container, .onetrust-close-btn-handler', function () {
  undockCookieBanner();
});

function applyConsent(hasConsent) {
  var foundExperienceInterval = setInterval(function() {
    var cerosFrames = document.querySelectorAll("iframe.ceros-experience");
    if (cerosFrames.length === 0) return; // no frames yet

    var cerosContainer = cerosFrames[0].parentNode;
    var expId = cerosContainer.getAttribute("id");
    if (expId) {
      clearInterval(foundExperienceInterval);
      // find experience
      CerosSDK.findExperience(expId)
        .done(function(experience) {
          experience.setUserConsentForAnalytics(hasConsent);
        })
        .fail(function(error) {
          console.error(error);
        });
    }
  }, 500);
}

// Run once at load with false (no consent by default)
applyConsent(false);

function OptanonWrapper() {
  // Get initial OnetrustActiveGroups ids
  if (typeof OptanonWrapperCount == 'undefined') {
    otGetInitialGrps();
  }

  //Delete cookies
  otDeleteCookie(otIniGrps);

  // Assign OnetrustActiveGroups to custom variable
  function otGetInitialGrps() {
    OptanonWrapperCount = '';
    otIniGrps = OnetrustActiveGroups;
    // console.log("otGetInitialGrps", otIniGrps)
  }

  function otDeleteCookie(iniOptGrpId) {
    var otDomainGrps = JSON.parse(JSON.stringify(Optanon.GetDomainData().Groups));
    var otDeletedGrpIds = otGetInactiveId(iniOptGrpId, OnetrustActiveGroups);
    if (otDeletedGrpIds.length != 0 && otDomainGrps.length != 0) {
      for (var i = 0; i < otDomainGrps.length; i++) {
        //Check if CustomGroupId matches
        if (
          otDomainGrps[i]['CustomGroupId'] != '' &&
          otDeletedGrpIds.includes(otDomainGrps[i]['CustomGroupId'])
        ) {
          for (var j = 0; j < otDomainGrps[i]['Cookies'].length; j++) {
            // console.log("otDeleteCookie",otDomainGrps[i]['Cookies'][j]['Name'])
            //Delete cookie
            eraseCookie(otDomainGrps[i]['Cookies'][j]['Name']);
          }
        }

        //Check if Hostid matches
        if (otDomainGrps[i]['Hosts'].length != 0) {
          for (var j = 0; j < otDomainGrps[i]['Hosts'].length; j++) {
            //Check if HostId presents in the deleted list and cookie array is not blank
            if (
              otDeletedGrpIds.includes(otDomainGrps[i]['Hosts'][j]['HostId']) &&
              otDomainGrps[i]['Hosts'][j]['Cookies'].length != 0
            ) {
              for (var k = 0; k < otDomainGrps[i]['Hosts'][j]['Cookies'].length; k++) {
                //Delete cookie
                eraseCookie(otDomainGrps[i]['Hosts'][j]['Cookies'][k]['Name']);
              }
            }
          }
        }
      }
    }
    otGetInitialGrps(); //Reassign new group ids
  }

  //Get inactive ids
  function otGetInactiveId(customIniId, otActiveGrp) {
    //Initial OnetrustActiveGroups
    // console.log("otGetInactiveId",customIniId)
    customIniId = customIniId.split(',');
    customIniId = customIniId.filter(Boolean);

    //After action OnetrustActiveGroups
    otActiveGrp = otActiveGrp.split(',');
    otActiveGrp = otActiveGrp.filter(Boolean);

    var result = [];
    for (var i = 0; i < customIniId.length; i++) {
      if (otActiveGrp.indexOf(customIniId[i]) <= -1) {
        result.push(customIniId[i]);
      }
    }
    return result;
  }

  //Delete cookie
  function eraseCookie(name) {
    //Delete root path cookies
    domainName = window.location.hostname;
    document.cookie = name + '=; Max-Age=-99999999; Path=/;Domain=' + domainName;
    document.cookie = name + '=; Max-Age=-99999999; Path=/;';

    //Delete LSO incase LSO being used, cna be commented out.
    localStorage.removeItem(name);

    //Check for the current path of the page
    pathArray = window.location.pathname.split('/');
    //Loop through path hierarchy and delete potential cookies at each path.
    for (var i = 0; i < pathArray.length; i++) {
      if (pathArray[i]) {
        //Build the path string from the Path Array e.g /site/login
        var currentPath = pathArray.slice(0, i + 1).join('/');
        document.cookie =
          name + '=; Max-Age=-99999999; Path=' + currentPath + ';Domain=' + domainName;
        document.cookie = name + '=; Max-Age=-99999999; Path=' + currentPath + ';';
        //Maybe path has a trailing slash!
        document.cookie =
          name + '=; Max-Age=-99999999; Path=' + currentPath + '/;Domain=' + domainName;
        document.cookie = name + '=; Max-Age=-99999999; Path=' + currentPath + '/;';
      }
    }
  }

  const hasConsent = OnetrustActiveGroups.indexOf('C0003') !== -1;
  applyConsent(hasConsent);

  // Send consent status to embedded Ceros iframe(s)
  document.querySelectorAll("iframe.ceros-experience").forEach(frame => {
    frame.contentWindow.postMessage({
      type: 'eloqua-consent',
      consentGiven: hasConsent
    }, '*');
  });

}

//Adds blank target
//sc_site is not going to work, cookie is httponly, will not be returned by document.cookie
// var cookieName = 'sc_site';
// var cookieValue = '';
// var cookieList = decodeURIComponent(document.cookie).split(';');
// for (var i = 0; i < cookieList.length; i++) {
//   var cookie = cookieList[i].trim();
//   if (cookie.startsWith(cookieName + '=')) {
//     cookieValue = cookie.substring(cookieName.length + 1);
//     break;
//   }
// }
// if (
//   cookieValue != '' &&
//   cookieValue.toLowerCase() !== 'kroll_ppc' &&
//   cookieValue.toLowerCase() !== 'kroll_careers'
// ) {
//   var currentLang = location.pathname.split('/')[1];
//   $('a[href]').each(function (index, item) {
//     var url = item.href;
//     if (url.includes(location.origin)) {
//       var urlObj = new URL(url);
//       if (urlObj.pathname.split('/')[1] !== currentLang) {
//         $(item).attr('target', '_blank');
//       }
//     }
//   });
// }

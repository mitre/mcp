// SMOOTH SCROLL
var $root = jQuery('html, body');

jQuery('a[href^="#"].scrollto').click(function () {
  var href = jQuery.attr(this, 'href');

  $root.animate(
      {
        scrollTop: jQuery(href).offset().top - 100,
      },
      300,
      function () {
        window.location.hash = href;
      }
  );

  return false;
});

// SMOOTH SCROLL WITH NO HASH

jQuery('a[href^="#"].scrolltonohash').click(function () {
  var href = jQuery.attr(this, 'href');

  $root.animate(
      {
        scrollTop: jQuery(href).offset().top - 100,
      },
      300
  );

  return false;
});


// PRODUCT PAGE ACCORDION
jQuery(window).on('load', function () {
  let accordions = document.querySelectorAll('.accordion');
  
  accordions.forEach(accordion => {
    let items = accordion.querySelectorAll('.accordion-item');
    let title = accordion.querySelectorAll('.accordion-item__title');

    function toggleAccordion() {
      let thisItem = this.parentNode;
      items.forEach((item) => {
        if (thisItem == item) {
          // if this item is equal to the clicked item, open it.
          thisItem.classList.toggle('active');
          return;
        }
        // otherwise, remove the open class
        item.classList.remove('active');
      });
    }
    title.forEach((question) => question.addEventListener('click', toggleAccordion));
  });
});

/*
// PRODUCT PAGE ACCORDION
let accordion = document.querySelector('.accordion');
if (accordion) {
  let items = accordion.querySelectorAll('.accordion-item');
  let title = accordion.querySelectorAll('.accordion-item__title');

  function toggleAccordion() {
    let thisItem = this.parentNode;
    items.forEach((item) => {
      if (thisItem == item) {
        // if this item is equal to the clicked item, open it.
        thisItem.classList.toggle('active');
        return;
      }
      // otherwise, remove the open class
      // item.classList.remove('active');
    });
  }
  title.forEach((question) => question.addEventListener('click', toggleAccordion));
}
*/

//  FORM label active
jQuery(window).on('load', function () {
  jQuery('.talktosales__selector').click(function () {
    if (jQuery(this).hasClass('talktosales__selector--checked')) {
      jQuery(this).removeClass('talktosales__selector--checked');
    } else {
      jQuery('.talktosales__selector').removeClass('talktosales__selector--checked');
      jQuery(this).addClass('talktosales__selector--checked');
    }
  });
});
// reports tabs

jQuery(document).ready(function () {
  var slidesOverflow = jQuery('.swiper__nav .swiper-button-disabled').length;
  if (slidesOverflow >= 2) {
    jQuery('.swiper-button-next').hide();
    jQuery('.swiper-button-prev').hide();
  }
});
jQuery(document).ready(function () {
  jQuery('.reports__list a').show();
  jQuery('a.lm-reports').hide();
  jQuery('a.lm-reports').click(function () {
    jQuery('.reports__list a').show();
    jQuery('a.lm-reports').hide();
  });
  if (location.hash === '') {
    jQuery('.tabs__list').find('a.reports__tab--all').addClass('tab--active');
    jQuery('a.lm-reports').show();
    jQuery('.reports-hub .reports__list a').hide();
    jQuery('.reports-hub .reports__list a:nth-child(1)').show();
    jQuery('.reports-hub .reports__list a:nth-child(2)').show();
    jQuery('.reports-hub .reports__list a:nth-child(3)').show();
    jQuery('.reports-hub .reports__list a:nth-child(4)').show();
    jQuery('.reports-hub .reports__list a:nth-child(5)').show();
    jQuery('.reports-hub .reports__list a:nth-child(6)').show();
    jQuery('.reports-hub .reports__list a:nth-child(7)').show();
    jQuery('.reports-hub .reports__list a:nth-child(8)').show();
    jQuery('.reports-hub .reports__list a:nth-child(9)').show();
    jQuery('.reports-hub .reports__list a:nth-child(10)').show();
    jQuery('.reports-hub .reports__list a:nth-child(11)').show();
    jQuery('.reports-hub .reports__list a:nth-child(12)').show();
  } else if (location.hash === '#threat-research') {
    jQuery('.tabs__list').find("a.reports__tab[id='#threat-research']").addClass('tab--active');
    jQuery(".reports__list a.reports__item-wrapper[id!='threat-research']").hide();
  } else if (location.hash === '#trend-report') {
    jQuery('.tabs__list').find("a.reports__tab[id='#trend-report']").addClass('tab--active');
    jQuery(".reports__list a.reports__item-wrapper[id!='trend-report']").hide();
  } else if (location.hash === '#analytical-report') {
    jQuery('.tabs__list').find("a.reports__tab[id='#analytical-report']").addClass('tab--active');
    jQuery(".reports__list a.reports__item-wrapper[id!='analytical-report']").hide();
  } else if (location.hash === '#white-paper') {
    jQuery('.tabs__list').find("a.reports__tab[id='#white-paper']").addClass('tab--active');
    jQuery(".reports__list a.reports__item-wrapper[id!='white-paper']").hide();
  }
  jQuery('.reports__tab').click(function () {
    if (jQuery(this).hasClass('reports__tab--all')) {
      history.replaceState(null, null, ' ');
      jQuery('.reports__tab').removeClass('tab--active');
      jQuery(this).toggleClass('tab--active');
      jQuery('.reports__list a').show();
      jQuery('a.lm-reports').show();
      jQuery('.reports-hub .reports__list a').hide();
      jQuery('.reports-hub .reports__list a:nth-child(1)').show();
      jQuery('.reports-hub .reports__list a:nth-child(2)').show();
      jQuery('.reports-hub .reports__list a:nth-child(3)').show();
      jQuery('.reports-hub .reports__list a:nth-child(4)').show();
      jQuery('.reports-hub .reports__list a:nth-child(5)').show();
      jQuery('.reports-hub .reports__list a:nth-child(6)').show();
      jQuery('.reports-hub .reports__list a:nth-child(7)').show();
      jQuery('.reports-hub .reports__list a:nth-child(8)').show();
      jQuery('.reports-hub .reports__list a:nth-child(9)').show();
      jQuery('.reports-hub .reports__list a:nth-child(10)').show();
      jQuery('.reports-hub .reports__list a:nth-child(11)').show();
      jQuery('.reports-hub .reports__list a:nth-child(12)').show();
    } else {
      let urlhash = jQuery(this).attr('id');
      let urlid = urlhash.substring(1);
      history.replaceState(null, null, urlhash);
      jQuery('.reports__tab').removeClass('tab--active');
      jQuery(this).toggleClass('tab--active');
      jQuery('.reports__list a.reports__item-wrapper').hide();
      jQuery('.reports__list a#' + urlid).show();
      jQuery('a.lm-reports').hide();
    }
    // jQuery('.reports__list a:not('urlid')'.attr(urlid).hide();
  });
});

//

jQuery(document).ready(function () {
  jQuery('.investigations__list a').show();
  jQuery('a.lm-investigations').hide();
  jQuery('a.lm-investigations').click(function () {
    jQuery('.investigations__list a').show();
    jQuery('a.lm-investigations').hide();
  });
  if (location.hash === '') {
    jQuery('.tabs__list').find('a.investigation__tab--all').addClass('tab--active');
    jQuery('a.lm-investigations').show();
    jQuery('.investigations-hub .investigations__list a').hide();

    jQuery('.investigations-hub .investigations__list a:nth-child(1)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(2)').show();
    /*
    jQuery('.investigations-hub .investigations__list a:nth-child(3)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(4)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(5)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(6)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(7)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(8)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(9)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(10)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(11)').show();
    jQuery('.investigations-hub .investigations__list a:nth-child(12)').show();
    */
  } else if (location.hash === '#bec') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#bec']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='bec']").hide();
  } else if (location.hash === '#botnet') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#botnet']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='botnet']").hide();
  } else if (location.hash === '#ddos') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#ddos']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='ddos']").hide();
  } else if (location.hash === '#malware') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#malware']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='malware']").hide();
  } else if (location.hash === '#android-trojans') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#android-trojans']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='android-trojans']").hide();
  } else if (location.hash === '#phishing') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#phishing']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='phishing']").hide();
  } else if (location.hash === '#scam') {
    jQuery('.tabs__list').find("a.investigation__tab[id='#scam']").addClass('tab--active');
    jQuery(".investigations__list a.investigations__item-wrapper[id!='scam']").hide();
  }

  jQuery('.investigation__tab').click(function () {
    if (jQuery(this).hasClass('investigation__tab--all')) {
      history.replaceState(null, null, ' ');
      jQuery('.investigation__tab').removeClass('tab--active');
      jQuery(this).toggleClass('tab--active');
      jQuery('.investigations__list a').show();
      jQuery('a.lm-investigations').show();
      jQuery('.investigations-hub .investigations__list a').hide();

      jQuery('.investigations-hub .investigations__list a:nth-child(1)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(2)').show();
      /*
      jQuery('.investigations-hub .investigations__list a:nth-child(3)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(4)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(5)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(6)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(7)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(8)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(9)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(10)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(11)').show();
      jQuery('.investigations-hub .investigations__list a:nth-child(12)').show();
      */
    } else {
      let urlhash = jQuery(this).attr('id');
      let urlid = urlhash.substring(1);
      history.replaceState(null, null, urlhash);
      jQuery('.investigation__tab').removeClass('tab--active');
      jQuery(this).toggleClass('tab--active');
      jQuery('.investigations__list a.investigations__item-wrapper').hide();
      jQuery('.investigations__list a#' + urlid).show();
      jQuery('a.lm-investigations').hide();
    }
    // jQuery('.investigations__list a:not('urlid')'.attr(urlid).hide();
  });
});

// Scheme toggles

// TI
jQuery('body').on('click', function (event) {
  if (!jQuery(event.target).is('.product-scheme--ti__group-toggle, .product-scheme__group--active, .product-scheme__group--active *')) {
    jQuery('.product-scheme--ti .product-scheme__toggles').find('.product-scheme__group-toggle--active').removeClass('product-scheme__group-toggle--active').addClass('product-scheme__group-toggle--default');
    jQuery('.product-scheme.product-scheme--ti').find('.product-scheme__group').removeClass('product-scheme__group--active');
  }
});
jQuery('.product-scheme--ti__group-toggle').click(function () {
  var index = jQuery('.product-scheme--ti .product-scheme__toggles div.product-scheme--ti__group-toggle').index(this);
  var index = index + 1;
  if (jQuery(this).hasClass('product-scheme__group-toggle--active')) {
    jQuery(this).toggleClass('product-scheme__group-toggle--active');
    jQuery('.product-scheme.product-scheme--ti').find('.product-scheme__group--active').removeClass('product-scheme__group--active');
    jQuery(this).addClass('product-scheme__group-toggle--default');
  } else {
    jQuery('.product-scheme--ti .product-scheme__toggles').find('.product-scheme__group-toggle--active').removeClass('product-scheme__group-toggle--active').addClass('product-scheme__group-toggle--default');
    jQuery('.product-scheme.product-scheme--ti').find('.product-scheme__group').removeClass('product-scheme__group--active');
    jQuery('.product-scheme.product-scheme--ti .product-scheme__groups')
        .find('.product-scheme__group:nth-child(' + index + ')')
        .toggleClass('product-scheme__group--active');
    jQuery(this).addClass('product-scheme__group-toggle--active');
    jQuery(this).removeClass('product-scheme__group-toggle--default');
  }
});

// MXDR
jQuery('body').on('click', function (event) {
  if (!jQuery(event.target).is('.product-scheme--mxdr__group-toggle, .product-scheme__group--active, .product-scheme__group--active *')) {
    jQuery('.product-scheme--mxdr .product-scheme__toggles').find('.product-scheme__group-toggle--active').removeClass('product-scheme__group-toggle--active').addClass('product-scheme__group-toggle--default');
    jQuery('.product-scheme.product-scheme--mxdr').find('.product-scheme__group').removeClass('product-scheme__group--active');
  }
});
jQuery('.product-scheme--mxdr__group-toggle').click(function () {
  var index = jQuery('.product-scheme--mxdr .product-scheme__toggles div.product-scheme--mxdr__group-toggle').index(this);
  var index = index + 1;
  if (jQuery(this).hasClass('product-scheme__group-toggle--active')) {
    jQuery(this).toggleClass('product-scheme__group-toggle--active');
    jQuery('.product-scheme.product-scheme--mxdr').find('.product-scheme__group--active').removeClass('product-scheme__group--active');
    jQuery(this).addClass('product-scheme__group-toggle--default');
  } else {
    jQuery('.product-scheme--mxdr .product-scheme__toggles').find('.product-scheme__group-toggle--active').removeClass('product-scheme__group-toggle--active').addClass('product-scheme__group-toggle--default');
    jQuery('.product-scheme.product-scheme--mxdr').find('.product-scheme__group').removeClass('product-scheme__group--active');
    jQuery('.product-scheme.product-scheme--mxdr .product-scheme__groups')
        .find('.product-scheme__group:nth-child(' + index + ')')
        .toggleClass('product-scheme__group--active');
    jQuery(this).addClass('product-scheme__group-toggle--active');
    jQuery(this).removeClass('product-scheme__group-toggle--default');
  }
});

jQuery('.product-scheme__group .product-scheme__group-name').click(function () {
  jQuery(this).toggleClass('product-scheme__group-name--dropdown');
  jQuery(this).closest('.product-scheme__group').find('.product-scheme__items').toggleClass('product-scheme__items--active');
});

// DRAG



// Threat Scheme

var threatschemes = new Swiper('.threat-schemes__swiper', {
  loop: true,
  roundLengths: true,
  slidesPerView: '1',
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  pagination: {
    el: '.threat-schemes__pagination',
    clickable: true,
    renderBullet: function (index, className) {
      return `
        <div class="swiper-pagination-bullet">
        
      </div>`;
    },
  },
});

// Threat Scheme END

// CARDS-CAROUSEL

var cardscarouselswiper = new Swiper('.cards-carousel__swiper', {
  roundLengths: true,
  slidesPerView: '4',
  breakpoints: {
    0: {
      slidesPerView: '1.25',
      spaceBetween: 8,
    },
    620: {
      slidesPerView: '3',
      spaceBetween: 24,
    },
    1270: {
      slidesPerView: '4',
      spaceBetween: 8,
    },
    2000: {
      slidesPerView: '4',
      spaceBetween: 16,
    },
  },
});

// CARDS-CAROUSEL END

// CAROUSEL

var urpcarousel = new Swiper('.urp-carousel-swiper', {
  loop: true,
  // loopedSlides: 10,
  // initialSlide: ,
  // centeredSlides: true,
  pagination: {
    el: '.swiper-pagination',
    clickable: true,
  },
  navigation: {
    nextEl: '.swiper__button-next',
    prevEl: '.swiper__button-prev',
  },
  breakpoints: {
    0: {
      slidesPerView: '1.25',
      slidesPerGroup: 1,
      centeredSlides: true,
      spaceBetween: 8,
    },
    768: {
      slidesPerView: '3',
      slidesPerGroup: 3,
      spaceBetween: 8,
    },
    1270: {
      slidesPerView: '3',
      slidesPerGroup: 3,
      spaceBetween: 8,
    },
    2000: {
      slidesPerView: '3',
      slidesPerGroup: 3,
      spaceBetween: 16,
    },
  },
});
var swiperMM = new Swiper('.swiperMM', {
  loop: true,
  autoHeight: true,
  roundLengths: true,
  autoplay:true,
  spaceBetween: 10,
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
});
// CAROUSEL END

// Trainers Education
// jQuery(window).on('load', function () {
var trainerscarousel = new Swiper('.trainer__swiper', {
  grabCursor: true,
  navigation: {
    nextEl: '.swiper-button-next',
    prevEl: '.swiper-button-prev',
  },
  pagination: {
    el: '.swiper-pagination',
    clickable: true,
  },
  breakpoints: {
    0: {
      slidesPerView: 'auto',
      freeMode: true,
      spaceBetween: 8,
      slidesPerGroup: 1,
    },
    620: {
      spaceBetween: 8,
      slidesPerView: 3,
      slidesPerGroup: 3,
    },
    1270: {
      spaceBetween: 16,
      slidesPerView: 3,
      slidesPerGroup: 3,
    },
    2000: {
      spaceBetween: 24,
      slidesPerView: 3,
      slidesPerGroup: 3,
    },
  },
});
// });

// Reports Carousel
// jQuery(window).on('load', function () {
var reportscarousel = new Swiper('.report__swiper', {
  grabCursor: true,
  navigation: {
    nextEl: '.swiper-button-next',
    prevEl: '.swiper-button-prev',
  },
  pagination: {
    el: '.swiper-pagination',
    clickable: true,
  },
  breakpoints: {
    0: {
      slidesPerView: 'auto',
      freeMode: true,
      spaceBetween: 8,
      slidesPerGroup: 1,
      watchOverflow: true,
    },
    620: {
      spaceBetween: 24,
      slidesPerView: 3,
      slidesPerGroup: 3,
      watchOverflow: true,
    },
    1270: {
      spaceBetween: 24,
      slidesPerView: 3,
      slidesPerGroup: 3,
      watchOverflow: true,
    },
    1725: {
      spaceBetween: 32,
      slidesPerView: 3,
      slidesPerGroup: 3,
      watchOverflow: true,
    },
    2000: {
      spaceBetween: 48,
      slidesPerView: 3,
      slidesPerGroup: 3,
      watchOverflow: true,
    },
  },
});
// });


// achievement Carousel
let swiperAchi = new Swiper('.swiper-achi', {
  grabCursor: true,
  freeMode: true,
  breakpoints: {
    0: {
      slidesPerView: "auto",
      slidesPerGroup: 1,
      spaceBetween: 8,
    },
    620: {
      slidesPerView: "auto",
      slidesPerGroup: 1,
      spaceBetween: 8,
    },
    1270: {
      slidesPerView: "auto",
      slidesPerGroup: 1,
      spaceBetween: 8,
    },
    1725: {
      slidesPerView: "auto",
      slidesPerGroup: 1,
      spaceBetween: 8,
    },
  },
});
//Infoblock carousel
let swiperInfo = new Swiper('.swiper-info', {
  grabCursor: true,
  autoplay: {
    delay: 5000,
  },
  loop:true,
  pagination: {
    el: '.swiper-pagination',
    clickable: true,
  },
  breakpoints: {
    0: {
      slidesPerView: 'auto',
      freeMode: true,
      spaceBetween: 8,
      slidesPerGroup: 1,
    },
    620: {
      spaceBetween: 8,
      slidesPerView: 3,
      slidesPerGroup: 3,
      freeMode: true,
    },
    1270: {
      slidesPerView: "auto",
      slidesPerGroup: 3,
      spaceBetween: 8,
      freeMode: true,
    },
    2000: {
      slidesPerView: "auto",
      slidesPerGroup: 3,
      spaceBetween: 8,
      freeMode: true,
    },
  },
});
// POPUP

jQuery('body').on('click', function (event) {
  if (!jQuery(event.target).is('.main-nav__report-wrapper, .main-nav__report-wrapper *, .main-nav__report-opener, .main-nav__report-opener *')) {
    jQuery('.main-nav__report.main-nav__report-popup').removeClass('main-nav__report-popup');
    jQuery('body').removeClass('while-popup');
  }
});

jQuery('body').on('click', function (event) {
  if (!jQuery(event.target).is('.main-nav__talktosales-wrapper, .main-nav__talktosales-wrapper *, .main-nav__talktosales-opener, .main-nav__talktosales-opener *')) {
    jQuery('.main-nav__talktosales.main-nav__talktosales-popup').removeClass('main-nav__talktosales-popup');
    jQuery('body').removeClass('while-popup');
  }
});

jQuery('body').on('click', function (event) {
  if (!jQuery(event.target).is('.main-nav__fighters-club-wrapper, .main-nav__fighters-club-wrapper *, .main-nav__fighters-club-opener, .main-nav__fighters-club-opener *')) {
    jQuery('.main-nav__fighters-club.main-nav__fighters-club-popup').removeClass('main-nav__fighters-club-popup');
    jQuery('body').removeClass('while-popup');
  }
});

jQuery('body').on('click', function (event) {
  if (!jQuery(event.target).is('.main-nav__consultation-wrapper, .main-nav__consultation-wrapper *, .main-nav__consultation-opener, .main-nav__consultation-opener *')) {
    jQuery('.main-nav__consultation.main-nav__consultation-popup').removeClass('main-nav__consultation-popup');
    jQuery('body').removeClass('while-popup');
  }
});

jQuery('.main-nav__report-opener').click(function () {
  jQuery('.main-nav__report').addClass('main-nav__report-popup');
  jQuery('body').toggleClass('while-popup');
});
jQuery('.main-nav__report-close').click(function () {
  jQuery('body').toggleClass('while-popup');
  jQuery('.main-nav__report').removeClass('main-nav__report-popup');
});

jQuery('.main-nav__talktosales-opener').click(function () {
  jQuery('.main-nav__talktosales').addClass('main-nav__talktosales-popup');
  jQuery('body').toggleClass('while-popup');
});
jQuery('.main-nav__talktosales-close').click(function () {
  jQuery('body').toggleClass('while-popup');
  jQuery('.main-nav__talktosales').removeClass('main-nav__talktosales-popup');
});

jQuery('.main-nav__fighters-club-opener').click(function () {
  jQuery('.main-nav__fighters-club').addClass('main-nav__fighters-club-popup');
  jQuery('body').toggleClass('while-popup');
});
jQuery('.main-nav__fighters-club-close').click(function () {
  jQuery('body').toggleClass('while-popup');
  jQuery('.main-nav__fighters-club').removeClass('main-nav__fighters-club-popup');
});

jQuery('.main-nav__consultation-opener').click(function () {
  jQuery('.main-nav__consultation').addClass('main-nav__consultation-popup');
  jQuery('body').toggleClass('while-popup');
});
jQuery('.main-nav__consultation-close').click(function () {
  jQuery('body').toggleClass('while-popup');
  jQuery('.main-nav__consultation').removeClass('main-nav__consultation-popup');
});

// SEARCH

jQuery('.main-nav__search-opener').click(function (e) {
  e.stopPropagation();
  jQuery('.main-nav__search').addClass('main-nav__search--active');
  jQuery('.main-nav__search').css('display', 'block');
  jQuery('.main-nav__search-close').addClass('main-nav__search-close--active');
  jQuery('.main-nav__under-search, .main-nav__search-opener').css({ opacity: '0', visibility: 'hidden', transition: '.25s all linear' });
});
jQuery('.main-nav__search-close').click(function () {
  jQuery('.main-nav__search').removeClass('main-nav__search--active');
  jQuery('.main-nav__search').css('display', 'none');
  jQuery('.main-nav__search-close').removeClass('main-nav__search-close--active');
  jQuery('.main-nav__under-search, .main-nav__search-opener').css({ opacity: '1', visibility: 'visible', transition: '.25s all linear' });
});

// Mobile Menu toggle

jQuery('.main-nav__mobile-menu').click(function () {
  jQuery('.main-nav__mobile-menu').toggleClass('main-nav__mobile-menu--active');
  jQuery('.main-nav__menu-list').toggleClass('main-nav__menu-list--dropdown');
  jQuery('.main-nav__actions').toggleClass('main-nav__actions--dropdown');
  jQuery('body').toggleClass('no-scroll');
  jQuery('.main-nav').toggleClass('main-nav--dropdown-active');
});

jQuery(document).ready(function () {
  jQuery('.main-nav__menu-item .body2').click(function () {
    jQuery(this).parent().toggleClass('main-nav__menu-item--mobile-active');
  });
});

// INFOTABS

var swiper = new Swiper('.infotabs-tabs', {
  loop: false,
  roundLengths: true,
  slidesPerView: 'auto',
  freeMode: true,
  watchSlidesProgress: true,
  watchSlidesVisibility: true,
  breakpoints: {
    0: {
      threshold: 0,
    },
    768: {
      threshold: 0,
    },
    1270: {
      threshold: 50,
    },
    2000: {
      threshold: 100,
    },
  },
});
var swiper2 = new Swiper('.infotabs-content', {
  loop: true,
  autoHeight: true,
  roundLengths: true,
  spaceBetween: 10,
  thumbs: {
    swiper: swiper,
  },
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  breakpoints: {
    0: {
      threshold: 50,
    },
    620: {
      threshold: 200,
    },
  },
});
var swiperTabsCharts = new Swiper('.infotabs-tabs-charts', {
  loop: false,
  roundLengths: true,
  slidesPerView: 'auto',
  freeMode: true,
  watchSlidesProgress: true,
  watchSlidesVisibility: true,
  breakpoints: {
    0: {
      threshold: 0,
    },
    768: {
      threshold: 0,
    },
    1270: {
      threshold: 50,
    },
    2000: {
      threshold: 100,
    },
  },
});

document.querySelectorAll('.infotabs-tabs-charts a').forEach(link => {
  link.addEventListener('click', function(event) {
    event.preventDefault(); 
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
  });
});

var swiperInfoCharts = new Swiper('.infotabs-content-charts', {
  loop: true,
  autoHeight: true,
  roundLengths: true,
  spaceBetween: 10,
  allowTouchMove: false, // Disable swiping
  simulateTouch: false, // Disable drag functionality
  on: {
    slideChange: function () {
      destroyCharts();
      initChart(); 
    },
  },
  thumbs: {
    swiper: swiperTabsCharts,
  },
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  breakpoints: {
    0: {
      threshold: 50,
    },
    620: {
      threshold: 200,
    },
  },
});

document.querySelectorAll('.key-single').forEach(button => {
  button.addEventListener('click', () => {
      const slideIndex = button.getAttribute('data-swiper-slide-index');

      document.querySelectorAll('.key-single').forEach(btn => btn.classList.remove('active'));

      button.classList.add('active');

      swiperInfoCharts.slideTo(slideIndex);

      const targetElement = document.querySelector('.product-tabs-section');
      if (targetElement) {
          targetElement.scrollIntoView({ behavior: 'smooth' });
      } else {
         
      }
  });
});

swiperInfoCharts.on('slideChange', () => {
  const activeIndex = swiperInfoCharts.activeIndex;
  document.querySelectorAll('.key-single').forEach((btn, index) => {
      btn.classList.toggle('active', index === activeIndex);
  });
});

var swiperTabs = new Swiper('.infotabs-tabs-new', {
  loop: false,
  roundLengths: true,
  slidesPerView: 'auto',
  freeMode: true,
  watchSlidesProgress: true,
  watchSlidesVisibility: true,
  breakpoints: {
    0: {
      threshold: 0,
    },
    768: {
      threshold: 0,
    },
    1270: {
      threshold: 50,
    },
    2000: {
      threshold: 100,
    },
  },
});
var swiperInfoTabs = new Swiper('.infotabs-content-new', {
  loop: true,
  autoHeight: true,
  roundLengths: true,
  spaceBetween: 10,
  thumbs: {
    swiper: swiperTabs,
  },
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  breakpoints: {
    0: {
      threshold: 50,
    },
    620: {
      threshold: 200,
    },
  },
});

var swiperTabs2 = new Swiper('.infotabs-tabs-new-modal', {
  loop: false,
  roundLengths: true,
  slidesPerView: 'auto',
  freeMode: true,
  watchSlidesProgress: true,
  watchSlidesVisibility: true,
  breakpoints: {
    0: {
      threshold: 0,
    },
    768: {
      threshold: 0,
    },
    1270: {
      threshold: 50,
    },
    2000: {
      threshold: 100,
    },
  },
});
var swiperInfoTabs2 = new Swiper('.infotabs-content-new-modal', {
  loop: true,
  autoHeight: true,
  roundLengths: true,
  spaceBetween: 10,
  thumbs: {
    swiper: swiperTabs2,
  },
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  breakpoints: {
    0: {
      threshold: 50,
    },
    620: {
      threshold: 200,
    },
  },
});

var swiper3 = new Swiper('.swiper3', {
  loop: true,
  autoHeight: true,
  roundLengths: true,
  spaceBetween: 10,
  thumbs: {
    swiper: swiper,
  },
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  breakpoints: {
    0: {
      threshold: 50,
    },
    620: {
      threshold: 200,
    },
  },
});

var swiper = new Swiper('.key-modules-tabs', {
  loop: false,
  roundLengths: true,
  slidesPerView: 'auto',
  freeMode: true,
  watchSlidesProgress: true,
  watchSlidesVisibility: true,
  breakpoints: {
    0: {
      threshold: 0,
    },
    768: {
      threshold: 0,
    },
    1270: {
      threshold: 50,
    },
    2000: {
      threshold: 100,
    },
  },
});

var swiper2 = new Swiper('.key-modules-content', {
  loop: true,
  roundLengths: true,
  spaceBetween: 10,
  thumbs: {
    swiper: swiper,
  },
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
});

// End INFOTABS

// MXDR PROGRESSTABS

// End MXDR PROGRESSTABS

// PROGRESSTABS

// document.addEventListener(
//   'mouseenter',
//   (event) => {
//     const el = event.target;
//     if (el && el.matches && el.matches('.progresstabs-content')) {
//       el.swiper.autoplay.stop();
//       el.classList.add('swiper-paused');

//       const activeNavItem = el.querySelector('.swiper-pagination-bullet-active');
//       activeNavItem.style.animationPlayState = 'paused';
//     }
//   },
//   true
// );
// document.addEventListener(
//   'mouseleave',
//   (event) => {
//     const el = event.target;
//     if (el && el.matches && el.matches('.progresstabs-content')) {
//       el.swiper.autoplay.start();
//       el.classList.remove('swiper-paused');

//       const activeNavItem = el.querySelector('.swiper-pagination-bullet-active');

//       setTimeout(() => {
//         activeNavItem.classList.add('swiper-pagination-bullet-active');
//       }, 0);
//     }
//   },
//   true
// );

// End PROGRESSTABS

// TAGCARDS

(function () {
  'use strict';

  // breakpoint where swiper will be destroyed
  const breakpoint = window.matchMedia('(min-width:620px)');

  // keep track of swiper instances to destroy later
  let swipertagcards;

  const breakpointChecker = function () {
    // if larger viewport
    if (breakpoint.matches === true) {
      // clean up old instances and inline styles when available
      if (swipertagcards !== undefined) swipertagcards.destroy(true, true);
      return;

      // else if a small viewport and single column layout needed
    } else if (breakpoint.matches === false) {
      // fire small viewport version of swiper
      return enableSwiper();
    }
  };

  const enableSwiper = function () {
    swipertagcards = new Swiper('.product-tagcards', {
      slidesPerView: 1,
      roundLengths: true,
      loop: true,
      pagination: {
        el: '.product-tagcards__swiper-pagination',
        clickable: true,
      },
      effect: 'fade',
      fadeEffect: {
        crossFade: true,
      },
    });
  };

  // keep an eye on viewport size changes
  breakpoint.addListener(breakpointChecker);

  // kickstart
  breakpointChecker();
})();

// End TAGCARDS

// INTEGRATIONS

(function () {
  'use strict';

  // breakpoint where swiper will be destroyed
  const breakpoint = window.matchMedia('(min-width:620px)');

  // keep track of swiper instances to destroy later
  let swiperintegrations;

  const breakpointChecker = function () {
    // if larger viewport
    if (breakpoint.matches === true) {
      // clean up old instances and inline styles when available
      if (swiperintegrations !== undefined) swiperintegrations.destroy(true, true);
      return;

      // else if a small viewport and single column layout needed
    } else if (breakpoint.matches === false) {
      // fire small viewport version of swiper
      return enableSwiper();
    }
  };

  const enableSwiper = function () {
    swiperintegrations = new Swiper('.product-integrations', {
      slidesPerView: 2,
      slidesPerGroup: 2,
      spaceBetween: 8,
      roundLengths: true,
      loop: false,
      pagination: {
        el: '.product-integrations__swiper-pagination',
        clickable: true,
      },
    });
  };

  // keep an eye on viewport size changes
  breakpoint.addListener(breakpointChecker);

  // kickstart
  breakpointChecker();
})();

// Load More press Releases
var pressPeleasesPage = 1;
jQuery('#load-more-press-releases').on('click', function () {
  pressPeleasesPage++;
  jQuery.ajax({
    type: 'POST',
    url: '/wp-admin/admin-ajax.php',
    dataType: 'html',
    data: {
      action: 'press_releases_load_more',
      paged: pressPeleasesPage,
    },
    success: function (res) {
      jQuery('.press-releases__list').append(res);
    },
  });
});

// Load More News
var newsPage = 1;
jQuery('#load-more-news').on('click', function () {
  newsPage++;
  jQuery.ajax({
    type: 'POST',
    url: '/wp-admin/admin-ajax.php',
    dataType: 'html',
    data: {
      action: 'news_load_more',
      paged: newsPage,
    },
    success: function (res) {
      jQuery('.news__list').append(res);
    },
  });
});

// jQuery('body, body *')
//   .not('.main-nav__search--active')
//   .click(function (e) {
//     e.stopPropagation();
//     jQuery('.main-nav__search').removeClass('main-nav__search--active');
//     jQuery('.main-nav__under-search, .main-nav__search-opener').css({ opacity: '1', visibility: 'visible', transition: '.25s all linear' });
//   });


//

let tabaccordion = document.querySelector('.tabaccordion');
if (tabaccordion) {
  let tabitems = tabaccordion.querySelectorAll('.tabaccordion-item');
  let tabtitle = tabaccordion.querySelectorAll('.tabaccordion-item__title');

  function toggleAccordion() {
    let thisItem = this.parentNode;

    tabitems.forEach((item) => {
      if (thisItem == item) {
        // if this item is equal to the clicked item, open it.
        thisItem.classList.toggle('active');
        $;
        return;
      }
      // otherwise, remove the open class
      item.classList.remove('active');
    });
  }

  tabtitle.forEach((question) => question.addEventListener('click', toggleAccordion));
}

/*
// mobile step image change
jQuery('.tabaccordion-item:nth-child(1) .tabaccordion-item__title').click(function () {
  jQuery(this).closest('.tab-content__wrapper').find('.tab-content__image--mobile').css('display', 'none');
  jQuery(this).closest('.tab-content__wrapper').find('.tab-content__image--mobile:nth-of-type(1)').css('display', 'block');
});
jQuery('.tabaccordion-item:nth-child(2) .tabaccordion-item__title').click(function () {
  jQuery(this).closest('.tab-content__wrapper').find('.tab-content__image--mobile').css('display', 'none');
  jQuery(this).closest('.tab-content__wrapper').find('.tab-content__image--mobile:nth-of-type(2)').css('display', 'block');
});
jQuery('.tabaccordion-item:nth-child(3) .tabaccordion-item__title').click(function () {
  jQuery(this).closest('.tab-content__wrapper').find('.tab-content__image--mobile').css('display', 'none');
  jQuery(this).closest('.tab-content__wrapper').find('.tab-content__image--mobile:nth-of-type(3)').css('display', 'block');
});
*/

jQuery(document).ready(function () {
  if (document.getElementById('cycle-tab-item-1')) {
    document.getElementById('cycle-tab-item-1').className = 'tab-content__progresstabs-tab cycle-tab-item active';
  }
  // Tab-Pane change function
  function tabChange() {
    var tabs = jQuery('.nav-tabs > li');
    var active = tabs.filter('.active');
    var next = active.next('li').length ? active.next('li').find('a') : tabs.filter(':first-child').find('a');
    next.tab('show');
  }

  // Tab Cycle function
  if (document.getElementById('cycle-tab-item-1')) {
    var tabCycle = setInterval(tabChange, 7000);
  }
  // Tab click event handler
  jQuery(function () {
    jQuery('.nav-tabs a').click(function (e) {
      e.preventDefault();
      clearInterval(tabCycle);
      jQuery(this).tab('show');
      tabCycle = setInterval(tabChange, 7000);
    });
  });
});


// REVIEWS

var reviewsswiper = new Swiper('.product-reviews__swiper', {
  loop: true,
  roundLengths: true,
  slidesPerView: '1',
  effect: 'fade',
  fadeEffect: {
    crossFade: true,
  },
  navigation: {
    nextEl: '.product-reviews__arrow-left',
    prevEl: '.product-reviews__arrow-right',
  },
});

// REVIEWS END

// new js

// tabs
let jsTriggers = document.querySelectorAll('.js-tab-trigger');
jsTriggers.forEach(function(trigger) {
  trigger.addEventListener('click', function() {

    let id = this.getAttribute('data-tab'),
        content = document.querySelector('.js-tab-content[data-tab="'+id+'"]'),
        activeTrigger = document.querySelector('.js-tab-trigger.active'),
        activeContent = document.querySelector('.js-tab-content.active');

    activeTrigger.classList.remove('active');
    trigger.classList.add('active');

    activeContent.classList.remove('active');
    content.classList.add('active');
  });
});

// tabs header swiper
var swiper = new Swiper('.tabs-header1', {
  slidesPerView: "auto",
  spaceBetween: 0,
  loop: false,
  freeMode: true,
  watchSlidesProgress: true,
  watchSlidesVisibility: true,
  roundLengths: true,
});
document.addEventListener('DOMContentLoaded', function() {
  const tagsWrapper = document.querySelector('.tags-header .swiper-wrapper');
  if (tagsWrapper) {

    setTimeout(() => {
      const slides = tagsWrapper.querySelectorAll('.swiper-slide');
      if (slides.length > 0) {
  
        slides.forEach(slide => {
          const clone = slide.cloneNode(true);
          tagsWrapper.appendChild(clone);
        });
        
        let position = 0;
        const speed = 0.5;
        const totalWidth = tagsWrapper.scrollWidth / 2; 
        
        function scrollTags() {
          position -= speed;
          tagsWrapper.style.transform = `translateX(${position}px)`;
          
          if (Math.abs(position) >= totalWidth) {
            position = 0;
          }
          
          requestAnimationFrame(scrollTags);
        }
        
        scrollTags();
      }
    }, 200);
  }
});
//Navigation
let swiperNav = new Swiper('.swiper-nav-slider', {
  grabCursor: true,
  autoHeight: true,
  effect: "fade",
  loop:true,
  observer: true,
  observeParents:true,
  pagination: {
    el: '.swiper-pagination',
    clickable: true,
  },
  autoplay: {
    delay: 5000,
    disableOnInteraction: 1,
  },
});

const swiperContainer = document.querySelector('.main-nav__menu-item--services1');

swiperContainer.addEventListener('mouseenter', function() {
  swiperContainer.classList.add('active');

  if (swiperContainer.classList.contains('active')) {
    swiperNav.update();
  }
});

swiperContainer.addEventListener('mouseleave', function() {
  swiperContainer.classList.remove('active');
  swiperNav.update();
});

//Youtube
let swiperYoutube = new Swiper('.swiper-youtube', {
  loop: true,
  freeMode: true,
  spaceBetween: 16,
  slidesPerView: 2,
  navigation: {
    nextEl: '.product-reviews__arrow-right',
    prevEl: '.product-reviews__arrow-left',
  },
  breakpoints: {
    0:{
      slidesPerView: 'auto',
    },
    768:{
      slidesPerView: '2',
    },
  },
});
//
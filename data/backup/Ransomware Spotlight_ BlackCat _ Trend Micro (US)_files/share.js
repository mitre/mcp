/* JAVASCRIPT/JQUERY Document */

/******************** SOCIAL MEDIA ********************/
$(document).on("click", ".share", function (e) {
    e.preventDefault();
    e.stopPropagation();
    var t = location.href;
    var n = $(this).attr("data-action");

    if (n == "twitter") {
       // var r = $(this).attr("data-title");
        var r = $('title').text();
        var i = $(this).attr("data-url");
        window.open("https://twitter.com/share?url=" + encodeURIComponent(t) + "&text=" + r + "", "twitterwindow", "height=255, width=550, top=" + ($(window).height() / 2 - 225) + ", left=" + ($(window).width() / 2 - 275) + ", toolbar=0, location=0, menubar=0, directories=0, scrollbars=0")
    } else if (n == "facebook") {

        var s = document.title; window.open("https://www.facebook.com/sharer.php?u=" + encodeURIComponent(t) + "&t=" + encodeURIComponent(s), "sharer", "status=0,width=626,height=436, top=" + ($(window).height() / 2 - 225) + ", left=" + ($(window).width() / 2 - 313) + ", toolbar=0, location=0, menubar=0, directories=0, scrollbars=0")

    } else if (n == "google") {

        window.open("https://plus.google.com/share?url=" + encodeURIComponent(t), "Google Share", "status=0,width=626,height=436, top=" + ($(window).height() / 2 - 225) + ", left=" + ($(window).width() / 2 - 313) + ", toolbar=0, location=0, menubar=0, directories=0, scrollbars=0")

    }
});

$(document).on("click", ".anchorInfog", function (e) {
    e.preventDefault();
    e.stopPropagation();
    $('.imgAttachHolder').fadeIn("slow");
    $('.imgAttachHolder textarea').val("<p><a href=\""+$(this).parent().attr("href")+"\"><img src=\""+$(this).parent().attr
("href")+"\" alt=\""+$('.articleHeader h1').text()+"\" style=\"width:669px;margin:0 auto;display:block;\"/></a></p>");
   

$('html,body').animate({ scrollTop: $('.imgAttachHolder').offset().top }, 'slow');
});

$(document).on("click", ".closeImg", function (e) {
    e.preventDefault();
    e.stopPropagation();
    $('.imgAttachHolder').fadeOut("slow");
    $('html,body').animate({ scrollTop: $('.anchorInfog').offset().top }, 'slow');
});

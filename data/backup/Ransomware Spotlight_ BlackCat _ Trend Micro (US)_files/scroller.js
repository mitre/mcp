$(document).ready(function () {


    if ($(".contentBoxSlide").length) {
     
        var widthSlideBlock = $('.DisplayBlockImages').css("width");
        widthSlideBlock = widthSlideBlock.replace("px", "");
        var count = $("#sliderimgs ul li").length;
       
        var sliderimgWidth = (((widthSlideBlock * 1) + 12) * count) * 5;
        $('#sliderimgs').css("width", sliderimgWidth + "px");
        var origContent = $('#sliderimgs ul').html();
        if (count > 4) {
            $('#sliderimgs ul').append(origContent);
        }
        var myTimeOut;
        var iterate = 0;
        var sliderimgWidthnow = 0;
        var leftnow = 0;
        var leftnowmove = leftnow;
        var refresh = 0;

        myTimeOut = setTimeout(function () {
            if (count > 4) {
                slideSlidermove(leftnowmove, iterate)
            }
        }, 3000);

  

        $('#sliderimgs').mouseover(function () {
            var count = $("#sliderimgs ul li").length;
            if (count > 4) {
                clearTimeout(myTimeOut);
            }
       });




        $('#sliderimgs').mouseout(function () {
            var count = $("#sliderimgs ul li").length;
        if (count > 4) {
            myTimeOut = setTimeout(function () {

                leftnowmove = $('#sliderimgs').css("margin-left").replace("px", "");
                leftnowmove = ((leftnowmove * 1));
                slideSlidermove(leftnowmove, $('#sliderimgs').attr("data-iterate"));
            }, 1000);

        }

        });



       if ($(".slidercontainer").html()) {
            $('.bxslider').bxSlider({
                minSlides: 2,
                maxSlides: 2,
                slideWidth: 315,
                slideMargin: 5,
                moveSlides: 1,
                touchEnabled:true,
                auto: true,
                autoControls: true
            });

           // $('.bxslider').css("-webkit-transform","translate3d(-633px, 0px, 0px)");
        }



    }




    function slideSlidermove(leftnowmove, iterate) {
        leftnowmove = (leftnowmove + (-173));
        $('#sliderimgs').addClass("run-animation");
        $('#sliderimgs').css( "margin-left", leftnowmove + "px")
        iterate = ((iterate * 1) + 1);
        $('#sliderimgs').attr("data-iterate", iterate);

     

        refresh = 0;
        if (iterate % count == 0 && iterate > 0) {
            $('#sliderimgs ul').html("");
            iterate = 0;
            widthSlideBlock = $('.DisplayBlockImages').css("width");
            sliderimgWidthnow = (((widthSlideBlock * 1) + 12) * count) * (iterate);
            $('#sliderimgs').css("margin-left", leftnowmove + "px")

           // $('#sliderimgs').css("width", "4375px");
            leftnowmove = 0;
            $('#sliderimgs ul').append(origContent);
            $('#sliderimgs ul').append(origContent);
           
            myTimeOut = setTimeout(function () {
               $('#sliderimgs').removeClass("run-animation");
                $('#sliderimgs').css("margin-left", "0px");
            }, 2000);

            refresh = 1;


        }



        if (refresh == 1) {
            myTimeOut = setTimeout(function () {
                slideSlidermove(leftnowmove, iterate);
            }, 3000);
        } else {
            myTimeOut = setTimeout(function () {
                slideSlidermove(leftnowmove, iterate);
            }, 3000);
        }


    }


   

   
        
   

//home banner
    if ($(".slidercontainerXXXX").html()) {

        var count = $("#sliderimgs ul li").length;

        var widthSlideBlock = $('.DisplayBlockImages').css("width");
        widthSlideBlock = widthSlideBlock.replace("px", "");
       

        var sliderimgWidth = (((widthSlideBlock * 1) + 12) * count) * 5;
        $('#sliderimgs').css("width", sliderimgWidth + "px");
        var origContent = $('#sliderimgs ul').html();
      
        if (count > 2) {
            $('#sliderimgs ul').append(origContent);
           
        }
        var myTimeOut;
        var iterate = 0;
        var sliderimgWidthnow = 0;
        var leftnow = 0;
        var leftnowmove = leftnow;
        var refresh = 0;

        myTimeOut = setTimeout(function () {
            if (count > 2) {
                homeSlideSliderMove(leftnowmove, iterate, count)
            }
        }, 3000);




        $('#sliderimgs').mouseover(function () {
           // var count = $("#sliderimgs ul li").length;
            if (count > 2) {
                clearTimeout(myTimeOut);
            }
        });




        $('#sliderimgs').mouseout(function () {
          //  var count = $("#sliderimgs ul li").length;
            if (count > 2) {
                myTimeOut = setTimeout(function () {

                    leftnowmove = $('#sliderimgs').css("margin-left").replace("px", "");
                    leftnowmove = ((leftnowmove * 1));
                    homeSlideSliderMove(leftnowmove, $('#sliderimgs').attr("data-iterate"), count);
                }, 1000);

            }

        });

        $('.arrowleft').on('click', function () {


            if ($('.arrowleft').attr("data-enable") == 1) {
                $('.arrowleft').attr("data-enable", "0");
                setInterval(function () { $('.arrowleft').attr("data-enable", "1"); }, 1500);

                clearTimeout(myTimeOut);
                leftnowmove = $('#sliderimgs').css("margin-left").replace("px", "");
                leftnowmove = ((leftnowmove * 1));
                homeSlideSliderMove(leftnowmove, $('#sliderimgs').attr("data-iterate"), count);


            }
        });



        function homeSlideSliderMove(leftnowmove, iterate, count) {
            leftnowmove = (leftnowmove + (-337));
            $('#sliderimgs').addClass("run-animation");
        // $('#sliderimgs').animate({ "margin-left": leftnowmove + "px" }, 900)
            $('#sliderimgs').css("margin-left", leftnowmove + "px");
            $('.arrowleft').attr("data-enable", "0");
            setInterval(function () { $('.arrowleft').attr("data-enable", "1"); }, 1500);
            iterate = ((iterate * 1) + 1);
            $('#sliderimgs').attr("data-iterate", iterate);
            refresh = 0;
          
            if (iterate % count == 0 && iterate > 0) {
                $('#sliderimgs ul').html("");
                iterate = 0;
                widthSlideBlock = $('.DisplayBlockImages').css("width");
                sliderimgWidthnow = (((widthSlideBlock * 1) + 12) * count) * (iterate);
                $('#sliderimgs').css("margin-left", leftnowmove + "px")
                
                $('#sliderimgs').css("width", "4375px");
                leftnowmove = 0;
                $('#sliderimgs ul').append(origContent);
                $('#sliderimgs ul').append(origContent);

                myTimeOut = setTimeout(function () {
                    $('#sliderimgs').removeClass("run-animation");
                    $('#sliderimgs').css("margin-left", "0px");
                }, 3000);
                    
                refresh = 1;
                

            }
           


           
           

           

            if (refresh == 1) {
          
                myTimeOut = setTimeout(function () {
                     homeSlideSliderMove(leftnowmove, iterate, count);
                }, 4000);
            } else {
                myTimeOut = setTimeout(function () {
                    homeSlideSliderMove(leftnowmove, iterate, count);
                }, 4000);
            }


        }




    }




});





(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[898],{50898:function(e,t,r){"use strict";t.J=void 0;var i=r(7424);Object.defineProperty(t,"J",{enumerable:!0,get:function(){return i.SiteResolver}})},37678:function(e,t,r){"use strict";var i=this&&this.__awaiter||function(e,t,r,i){return new(r||(r=Promise))(function(n,o){function a(e){try{u(i.next(e))}catch(e){o(e)}}function s(e){try{u(i.throw(e))}catch(e){o(e)}}function u(e){var t;e.done?n(e.value):((t=e.value)instanceof r?t:new r(function(e){e(t)})).then(a,s)}u((i=i.apply(e,t||[])).next())})},n=this&&this.__importDefault||function(e){return e&&e.__esModule?e:{default:e}};Object.defineProperty(t,"__esModule",{value:!0}),t.GraphQLErrorPagesService=void 0;let o=r(56489),a=r(63204),s=n(r(56907)),u=`
  query ErrorPagesQuery($siteName: String!, $language: String!) {
    site {
      siteInfo(site: $siteName) {
        errorHandling(language: $language) {
          notFoundPage {
            rendered
          }
          notFoundPagePath
          serverErrorPage {
            rendered
          }
          serverErrorPagePath
        }
      }
    }
  }
`;class c{constructor(e){this.options=e,this.graphQLClient=this.getGraphQLClient()}get query(){return u}fetchErrorPages(){return i(this,void 0,void 0,function*(){let e=this.options.siteName,t=this.options.language;if(!e)throw Error(a.siteNameError);return this.graphQLClient.request(this.query,{siteName:e,language:t}).then(e=>e.site.siteInfo?e.site.siteInfo.errorHandling:null).catch(e=>Promise.reject(e))})}getGraphQLClient(){if(!this.options.endpoint){if(!this.options.clientFactory)throw Error("You should provide either an endpoint and apiKey, or a clientFactory.");return this.options.clientFactory({debugger:s.default.errorpages,retries:this.options.retries,retryStrategy:this.options.retryStrategy})}return new o.GraphQLRequestClient(this.options.endpoint,{apiKey:this.options.apiKey,debugger:s.default.errorpages,retries:this.options.retries,retryStrategy:this.options.retryStrategy})}}t.GraphQLErrorPagesService=c},99938:function(e,t,r){"use strict";var i=this&&this.__awaiter||function(e,t,r,i){return new(r||(r=Promise))(function(n,o){function a(e){try{u(i.next(e))}catch(e){o(e)}}function s(e){try{u(i.throw(e))}catch(e){o(e)}}function u(e){var t;e.done?n(e.value):((t=e.value)instanceof r?t:new r(function(e){e(t)})).then(a,s)}u((i=i.apply(e,t||[])).next())})},n=this&&this.__importDefault||function(e){return e&&e.__esModule?e:{default:e}};Object.defineProperty(t,"__esModule",{value:!0}),t.GraphQLRedirectsService=t.REDIRECT_TYPE_SERVER_TRANSFER=t.REDIRECT_TYPE_302=t.REDIRECT_TYPE_301=void 0;let o=r(56489),a=r(63204),s=n(r(56907)),u=r(24559);t.REDIRECT_TYPE_301="REDIRECT_301",t.REDIRECT_TYPE_302="REDIRECT_302",t.REDIRECT_TYPE_SERVER_TRANSFER="SERVER_TRANSFER";let c=`
  query RedirectsQuery($siteName: String!) {
    site {
      siteInfo(site: $siteName) {
        redirects {
          pattern
          target
          redirectType
          isQueryStringPreserved
          locale
        }
      }
    }
  }
`;class h{constructor(e){this.options=e,this.graphQLClient=this.getGraphQLClient(),this.cache=this.getCacheClient()}get query(){return c}fetchRedirects(e){var t,r;return i(this,void 0,void 0,function*(){if(!e)throw Error(a.siteNameError);let i=`redirects-${e}`,n=this.cache.getCacheValue(i);return n||(n=yield this.graphQLClient.request(this.query,{siteName:e}),this.cache.setCacheValue(i,n)),(null===(r=null===(t=null==n?void 0:n.site)||void 0===t?void 0:t.siteInfo)||void 0===r?void 0:r.redirects)||[]})}getGraphQLClient(){if(!this.options.endpoint){if(!this.options.clientFactory)throw Error("You should provide either an endpoint and apiKey, or a clientFactory.");return this.options.clientFactory({debugger:s.default.redirects,fetch:this.options.fetch})}return new o.GraphQLRequestClient(this.options.endpoint,{apiKey:this.options.apiKey,debugger:s.default.redirects,fetch:this.options.fetch})}getCacheClient(){var e,t;return new u.MemoryCacheClient({cacheEnabled:null===(e=this.options.cacheEnabled)||void 0===e||e,cacheTimeout:null!==(t=this.options.cacheTimeout)&&void 0!==t?t:10})}}t.GraphQLRedirectsService=h},83484:function(e,t,r){"use strict";var i=this&&this.__awaiter||function(e,t,r,i){return new(r||(r=Promise))(function(n,o){function a(e){try{u(i.next(e))}catch(e){o(e)}}function s(e){try{u(i.throw(e))}catch(e){o(e)}}function u(e){var t;e.done?n(e.value):((t=e.value)instanceof r?t:new r(function(e){e(t)})).then(a,s)}u((i=i.apply(e,t||[])).next())})},n=this&&this.__importDefault||function(e){return e&&e.__esModule?e:{default:e}};Object.defineProperty(t,"__esModule",{value:!0}),t.GraphQLRobotsService=void 0;let o=r(56489),a=r(63204),s=n(r(56907)),u=`
  query RobotsQuery($siteName: String!) {
    site {
      siteInfo(site: $siteName) {
        robots
      }
    }
  }
`;class c{constructor(e){this.options=e,this.graphQLClient=this.getGraphQLClient()}get query(){return u}fetchRobots(){return i(this,void 0,void 0,function*(){let e=this.options.siteName;if(!e)throw Error(a.siteNameError);let t=this.graphQLClient.request(this.query,{siteName:e});try{return t.then(e=>{var t,r;return null===(r=null===(t=null==e?void 0:e.site)||void 0===t?void 0:t.siteInfo)||void 0===r?void 0:r.robots})}catch(e){return Promise.reject(e)}})}getGraphQLClient(){if(!this.options.endpoint){if(!this.options.clientFactory)throw Error("You should provide either an endpoint and apiKey, or a clientFactory.");return this.options.clientFactory({debugger:s.default.robots})}return new o.GraphQLRequestClient(this.options.endpoint,{apiKey:this.options.apiKey,debugger:s.default.robots})}}t.GraphQLRobotsService=c},88692:function(e,t,r){"use strict";var i=r(34155),n=this&&this.__awaiter||function(e,t,r,i){return new(r||(r=Promise))(function(n,o){function a(e){try{u(i.next(e))}catch(e){o(e)}}function s(e){try{u(i.throw(e))}catch(e){o(e)}}function u(e){var t;e.done?n(e.value):((t=e.value)instanceof r?t:new r(function(e){e(t)})).then(a,s)}u((i=i.apply(e,t||[])).next())})},o=this&&this.__importDefault||function(e){return e&&e.__esModule?e:{default:e}};Object.defineProperty(t,"__esModule",{value:!0}),t.GraphQLSiteInfoService=void 0;let a=r(56489),s=o(r(56907)),u=r(24559),c=`
  query($pageSize: Int = 10, $after: String) {
    search(
      where: {
        AND: [
          { name: "_templates", value: "E46F3AF2-39FA-4866-A157-7017C4B2A40C", operator: CONTAINS }
          { name: "_path", value: "0DE95AE4-41AB-4D01-9EB0-67441B7C2450", operator: CONTAINS }
        ]
      }
      first: $pageSize
      after: $after
    ) {
      pageInfo {
        endCursor
        hasNext
      }
      results {
        ... on Item {
          name: field(name: "SiteName") {
            value
          }
          hostName: field(name: "Hostname") {
            value
          }
          language: field(name: "Language") {
            value
          }
        }
      }
    }
  }
`,h=`
  query {
    site {
      siteInfoCollection {
        name
        hostName: hostname
        language
      }
    }
  }
`;class l{constructor(e){this.config=e,this.graphQLClient=this.getGraphQLClient(),this.cache=this.getCacheClient()}get query(){return c}get siteQuery(){return h}fetchSiteInfo(){return n(this,void 0,void 0,function*(){let e=this.cache.getCacheValue(this.getCacheKey());if(e)return e;if(i.env.SITECORE)return s.default.multisite("Skipping site information fetch (building on XM Cloud)"),[];let t=this.config.useSiteQuery?yield this.fetchWithSiteQuery():yield this.fetchWithDefaultQuery();return this.cache.setCacheValue(this.getCacheKey(),t),t})}fetchWithDefaultQuery(){var e,t;return n(this,void 0,void 0,function*(){let r=[],i=!0,n="";for(;i;){let o=yield this.graphQLClient.request(this.query,{pageSize:this.config.pageSize,after:n}),a=null===(t=null===(e=null==o?void 0:o.search)||void 0===e?void 0:e.results)||void 0===t?void 0:t.reduce((e,t)=>(e.push({name:t.name.value,hostName:t.hostName.value,language:t.language.value}),e),[]);r.push(...a),i=o.search.pageInfo.hasNext,n=o.search.pageInfo.endCursor}return r})}fetchWithSiteQuery(){var e,t;return n(this,void 0,void 0,function*(){let r=yield this.graphQLClient.request(this.siteQuery);return null===(t=null===(e=null==r?void 0:r.site)||void 0===e?void 0:e.siteInfoCollection)||void 0===t?void 0:t.reduce((e,t)=>("website"!==t.name&&e.push({name:t.name,hostName:t.hostName,language:t.language}),e),[])})}getCacheClient(){var e,t;return new u.MemoryCacheClient({cacheEnabled:null===(e=this.config.cacheEnabled)||void 0===e||e,cacheTimeout:null!==(t=this.config.cacheTimeout)&&void 0!==t?t:10})}getGraphQLClient(){if(!this.config.endpoint){if(!this.config.clientFactory)throw Error("You should provide either an endpoint and apiKey, or a clientFactory.");return this.config.clientFactory({debugger:s.default.multisite})}return new a.GraphQLRequestClient(this.config.endpoint,{apiKey:this.config.apiKey,debugger:s.default.multisite})}getCacheKey(){return"siteinfo-service-cache"}}t.GraphQLSiteInfoService=l},88277:function(e,t,r){"use strict";var i=this&&this.__awaiter||function(e,t,r,i){return new(r||(r=Promise))(function(n,o){function a(e){try{u(i.next(e))}catch(e){o(e)}}function s(e){try{u(i.throw(e))}catch(e){o(e)}}function u(e){var t;e.done?n(e.value):((t=e.value)instanceof r?t:new r(function(e){e(t)})).then(a,s)}u((i=i.apply(e,t||[])).next())})},n=this&&this.__importDefault||function(e){return e&&e.__esModule?e:{default:e}};Object.defineProperty(t,"__esModule",{value:!0}),t.GraphQLSitemapXmlService=void 0;let o=r(56489),a=r(63204),s=n(r(56907)),u=`
  query SitemapQuery($siteName: String!) {
    site {
      siteInfo(site: $siteName) {
        sitemap
      }
    }
  }
`;class c{constructor(e){this.options=e,this.graphQLClient=this.getGraphQLClient()}get query(){return u}fetchSitemaps(){return i(this,void 0,void 0,function*(){let e=this.options.siteName;if(!e)throw Error(a.siteNameError);let t=this.graphQLClient.request(this.query,{siteName:e});try{return t.then(e=>e.site.siteInfo.sitemap)}catch(e){return Promise.reject(e)}})}getSitemap(e){return i(this,void 0,void 0,function*(){let t=`sitemap${e}.xml`;return(yield this.fetchSitemaps()).find(e=>e.includes(t))})}getGraphQLClient(){if(!this.options.endpoint){if(!this.options.clientFactory)throw Error("You should provide either an endpoint and apiKey, or a clientFactory.");return this.options.clientFactory({debugger:s.default.sitemap})}return new o.GraphQLRequestClient(this.options.endpoint,{apiKey:this.options.apiKey,debugger:s.default.sitemap})}}t.GraphQLSitemapXmlService=c},39520:function(e,t,r){"use strict";Object.defineProperty(t,"__esModule",{value:!0}),t.SiteResolver=t.normalizeSiteRewrite=t.getSiteRewriteData=t.getSiteRewrite=t.GraphQLSiteInfoService=t.GraphQLErrorPagesService=t.GraphQLSitemapXmlService=t.GraphQLRedirectsService=t.REDIRECT_TYPE_SERVER_TRANSFER=t.REDIRECT_TYPE_302=t.REDIRECT_TYPE_301=t.GraphQLRobotsService=void 0;var i=r(83484);Object.defineProperty(t,"GraphQLRobotsService",{enumerable:!0,get:function(){return i.GraphQLRobotsService}});var n=r(99938);Object.defineProperty(t,"REDIRECT_TYPE_301",{enumerable:!0,get:function(){return n.REDIRECT_TYPE_301}}),Object.defineProperty(t,"REDIRECT_TYPE_302",{enumerable:!0,get:function(){return n.REDIRECT_TYPE_302}}),Object.defineProperty(t,"REDIRECT_TYPE_SERVER_TRANSFER",{enumerable:!0,get:function(){return n.REDIRECT_TYPE_SERVER_TRANSFER}}),Object.defineProperty(t,"GraphQLRedirectsService",{enumerable:!0,get:function(){return n.GraphQLRedirectsService}});var o=r(88277);Object.defineProperty(t,"GraphQLSitemapXmlService",{enumerable:!0,get:function(){return o.GraphQLSitemapXmlService}});var a=r(37678);Object.defineProperty(t,"GraphQLErrorPagesService",{enumerable:!0,get:function(){return a.GraphQLErrorPagesService}});var s=r(88692);Object.defineProperty(t,"GraphQLSiteInfoService",{enumerable:!0,get:function(){return s.GraphQLSiteInfoService}});var u=r(63085);Object.defineProperty(t,"getSiteRewrite",{enumerable:!0,get:function(){return u.getSiteRewrite}}),Object.defineProperty(t,"getSiteRewriteData",{enumerable:!0,get:function(){return u.getSiteRewriteData}}),Object.defineProperty(t,"normalizeSiteRewrite",{enumerable:!0,get:function(){return u.normalizeSiteRewrite}});var c=r(27607);Object.defineProperty(t,"SiteResolver",{enumerable:!0,get:function(){return c.SiteResolver}})},27607:function(e,t){"use strict";Object.defineProperty(t,"__esModule",{value:!0}),t.SiteResolver=void 0;let r=/\||,|;/g;class i{constructor(e){this.sites=e,this.getByHost=e=>{for(let[t,r]of this.getHostMap())if(this.matchesPattern(e,t))return r;throw Error(`Could not resolve site for host ${e}`)},this.getByName=e=>{let t=this.sites.find(t=>t.name.toLocaleLowerCase()===e.toLocaleLowerCase());if(!t)throw Error(`Could not resolve site for name ${e}`);return t},this.getHostMap=()=>{let e=new Map;return this.sites.forEach(t=>{t.hostName.replace(/\s/g,"").toLocaleLowerCase().split(r).forEach(r=>{e.has(r)||e.set(r,t)})}),new Map(Array.from(e).sort((e,t)=>e[0].length===t[0].length?(e[0].match(/\*/g)||[]).length-(t[0].match(/\*/g)||[]).length:t[0].length-e[0].length))}}matchesPattern(e,t){let r=t.replace(/\./g,"\\.").replace(/\*/g,".*"),i=RegExp(`^${r}$`,"gi");return!!e.match(i)}}t.SiteResolver=i},63085:function(e,t){"use strict";Object.defineProperty(t,"__esModule",{value:!0}),t.normalizeSiteRewrite=t.getSiteRewriteData=t.getSiteRewrite=t.SITE_PREFIX=void 0,t.SITE_PREFIX="_site_",t.getSiteRewrite=function(e,r){let i=e.startsWith("/")?e:"/"+e;return`/${t.SITE_PREFIX}${r.siteName}${i}`},t.getSiteRewriteData=function(e,r){let i={siteName:r},n=(e.endsWith("/")?e:e+"/").match(`${t.SITE_PREFIX}(.*?)\\/`);return n&&""!==n[1]&&(i.siteName=n[1]),i},t.normalizeSiteRewrite=function(e){let r=e.match(`${t.SITE_PREFIX}.*?(?:\\/|$)`);return null===r?e:e.replace(r[0],"")}},7424:function(e,t,r){e.exports=r(39520)}}]);
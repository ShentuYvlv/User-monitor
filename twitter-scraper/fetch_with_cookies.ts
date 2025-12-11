// 手动定义构建时变量
(global as any).PLATFORM_NODE = true;

import { Scraper } from './src/scraper';
import { HttpsProxyAgent } from 'https-proxy-agent';
import fetch from 'cross-fetch';
import * as dotenv from 'dotenv';
import { Cookie } from 'tough-cookie';

dotenv.config();

// 代理配置
const PROXY_PORT = 10808;
const PROXY_URL = `http://127.0.0.1:${PROXY_PORT}`;

// 必须的 Cookies
// 可以在浏览器 F12 -> Application -> Cookies -> https://x.com 中找到
const AUTH_TOKEN = process.env.TWITTER_AUTH_TOKEN || '';
const CT0 = process.env.TWITTER_CT0 || '';

// 目标用户
const TARGET_USER = process.argv[2] || 'sue471929950426';
const TWEET_COUNT = 20;

async function main() {
    console.log(`=== Twitter Scraper (Cookie Mode) ===`);
    console.log(`代理地址: ${PROXY_URL}`);
    console.log(`目标用户: ${TARGET_USER}`);

    if (!AUTH_TOKEN || !CT0) {
        console.error('\n[错误] 未提供完整的 Cookie 信息！');
        console.error('请设置环境变量 TWITTER_AUTH_TOKEN 和 TWITTER_CT0。');
        console.error('获取方法: 浏览器登录 Twitter -> F12 -> Application -> Cookies -> 查找 auth_token 和 ct0');
        process.exit(1);
    }

    // 1. 配置代理 Agent
    const agent = new HttpsProxyAgent(PROXY_URL);

    // 2. 初始化 Scraper
    // 提示: 如果你被 CF 拦截严重，可能需要在这里通过 transform 修改 User-Agent
    const scraper = new Scraper({
        fetch: (url, init) => {
            return fetch(url, {
                ...init,
                agent: agent,
            } as any);
        }
    });

    // 3. 注入 Cookies (绕过登录)
    console.log('\n正在注入 Cookies...');
    
    // 访问私有属性 auth (TypeScript hack)
    const auth = (scraper as any).auth;
    const jar = auth.cookieJar();

    // 手动构造并设置关键 Cookie
    try {
        const domain = 'x.com';
        const url = 'https://x.com';

        const authTokenCookie = new Cookie({
            key: 'auth_token',
            value: AUTH_TOKEN,
            domain: domain,
            path: '/',
            secure: true,
            httpOnly: true
        });

        const ct0Cookie = new Cookie({
            key: 'ct0',
            value: CT0,
            domain: domain,
            path: '/',
            secure: true
        });

        jar.setCookieSync(authTokenCookie, url);
        jar.setCookieSync(ct0Cookie, url);

        console.log(`成功注入 auth_token 和 ct0。`);
    } catch (e) {
        console.error('设置 Cookie 失败:', e);
        process.exit(1);
    }

    // 验证一下
    const cookies = await auth.getCookies();
    const hasAuthToken = cookies.some((c: any) => c.key === 'auth_token');
    const hasCt0 = cookies.some((c: any) => c.key === 'ct0');

    if (!hasAuthToken || !hasCt0) {
        console.warn('警告: 缺少关键 Cookie (auth_token 或 ct0)，抓取可能会失败！');
    }

    // 4. 获取推文
    console.log(`\n正在抓取用户 @${TARGET_USER} 的最近 ${TWEET_COUNT} 条推文...`);
    
    let count = 0;
    try {
        const tweets = scraper.getTweets(TARGET_USER, TWEET_COUNT);
        
        for await (const tweet of tweets) {
            count++;
            const timestamp = tweet.timestamp ? new Date(tweet.timestamp * 1000).toLocaleString() : '未知时间';
            
            console.log(`\n[${count}] --------------------------------------------------`);
            console.log(`ID: ${tweet.id}`);
            console.log(`时间: ${timestamp}`);
            console.log(`内容: \n${tweet.text}`);
            
             if (tweet.photos && tweet.photos.length > 0) {
                 console.log(`图片: ${tweet.photos.map(p => p.url).join(', ')}`);
            }
            if (tweet.videos && tweet.videos.length > 0) {
                console.log(`视频: ${tweet.videos.map(v => v.url).join(', ')}`);
            }
            
            console.log(`数据: 💬 ${tweet.replies} | 🔁 ${tweet.retweets} | ❤️ ${tweet.likes} | 👁️ ${tweet.views || 'N/A'}`);
        }

        if (count === 0) {
            console.log('\n未找到任何推文。可能原因：');
            console.log('1. Cookie 失效或权限不足');
            console.log('2. 账号被封禁/锁推');
            console.log('3. 仍然被 Cloudflare 拦截 (尝试更新 User-Agent)');
        } else {
            console.log(`\n抓取完成，共获取 ${count} 条推文。`);
        }

    } catch (err) {
        console.error('\n抓取过程中发生错误:', err);
        if (err instanceof Error) {
            console.error('错误信息:', err.message);
        }
    }
}

main();

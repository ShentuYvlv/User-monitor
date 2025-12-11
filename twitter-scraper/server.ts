// 手动定义构建时变量
(global as any).PLATFORM_NODE = true;

import express from 'express';
import cors from 'cors';
import bodyParser from 'body-parser';
import { Scraper } from './src/scraper';
import { HttpsProxyAgent } from 'https-proxy-agent';
import fetch from 'cross-fetch';
import * as dotenv from 'dotenv';
import { Cookie } from 'tough-cookie';

dotenv.config();

const app = express();
const PORT = 3000;

app.use(cors());
app.use(bodyParser.json());

// 代理配置
const PROXY_URL = process.env.TWITTER_PROXY_URL;

// Twitter 固定 Bearer Token (Web 端通用)
const BEARER_TOKEN = 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';

app.post('/scrape', async (req, res) => {
    let { username, limit = 20, auth_token, ct0 } = req.body;

    // 1. 数据清洗与回退逻辑
    if (username) username = username.trim();
    
    // 如果请求体没传，尝试从环境变量读取
    if (!auth_token) auth_token = process.env.TWITTER_AUTH_TOKEN;
    if (!ct0) ct0 = process.env.TWITTER_CT0;

    if (auth_token) auth_token = auth_token.trim();
    if (ct0) ct0 = ct0.trim();

    console.log(`[Twitter Scraper] Request: User=${username}, Limit=${limit}`);

    if (!username || !auth_token || !ct0) {
        return res.status(400).json({ error: 'Missing username, auth_token, or ct0 (and not set in env)' });
    }

    // 2. 关键调试日志：打印 Cookie 的前几位，方便比对
    console.log(`[Debug] auth_token prefix: ${auth_token.substring(0, 5)}...`);
    console.log(`[Debug] ct0 prefix:        ${ct0.substring(0, 5)}...`);

    try {
        // 配置 Agent
        const agent = PROXY_URL ? new HttpsProxyAgent(PROXY_URL) : undefined;
        if (PROXY_URL) console.log(`[Twitter Scraper] Using Proxy: ${PROXY_URL}`);

        // 初始化 Scraper，回归简单模式，只配置代理
        const scraper = new Scraper({
            fetch: ((url: string, init: any) => {
                // 不要手动设置 headers，让库自己处理
                return fetch(url, {
                    ...init,
                    agent: agent,
                } as any);
            }) as any
        });

        // 注入 Cookies 到 CookieJar (用于维持会话状态)
        const auth = (scraper as any).auth;
        const jar = auth.cookieJar();
        const url = 'https://x.com';
        const domain = 'x.com';

        jar.setCookieSync(new Cookie({ key: 'auth_token', value: auth_token, domain, path: '/', secure: true, httpOnly: true }), url);
        jar.setCookieSync(new Cookie({ key: 'ct0', value: ct0, domain, path: '/', secure: true }), url);

        console.log(`[Twitter Scraper] Cookies injected & Headers configured.`);

        // 执行抓取
        const tweetsGenerator = scraper.getTweets(username, limit);
        const tweets = [];

        for await (const tweet of tweetsGenerator) {
            tweets.push({
                id: tweet.id,
                text: tweet.text,
                timestamp: tweet.timestamp,
                photos: tweet.photos,
                videos: tweet.videos,
                replies: tweet.replies,
                retweets: tweet.retweets,
                likes: tweet.likes,
                views: tweet.views,
                permanentUrl: tweet.permanentUrl,
                isRetweet: tweet.isRetweet,
                isPin: tweet.isPin
            });
        }

        console.log(`[Twitter Scraper] Success: Fetched ${tweets.length} tweets.`);
        return res.json({ success: true, count: tweets.length, tweets: tweets });

    } catch (error: any) {
        console.error('[Twitter Scraper] Error:', error);
        // 打印更详细的错误堆栈
        if (error.cause) console.error('Cause:', error.cause);
        return res.status(500).json({ error: error.message || 'Internal Server Error' });
    }
});

app.listen(PORT, () => {
    console.log(`[Twitter Scraper] Service running on port ${PORT}`);
});
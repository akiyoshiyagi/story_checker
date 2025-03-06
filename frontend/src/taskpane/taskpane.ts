/*
 * Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the MIT license.
 * See LICENSE in the project root for license information.
 */

/* global document, Office, Word */

// 箇条書きの階層構造を表すインターフェース
interface Body {
  content: string;
}

interface Message {
  content: string;
  bodies: Body[];
}

interface Summary {
  content: string;
  messages: Message[];
}

interface BulletPointsRequest {
  summaries: Summary[];
  title?: string;
}

// 評価範囲の列挙型
enum EvaluationScope {
  DOCUMENT_WIDE = "document_wide",
  ALL_SUMMARIES = "all_summaries",
  SUMMARY_PAIRS = "summary_pairs",
  SUMMARY_WITH_MESSAGES = "summary_with_messages",
  MESSAGES_UNDER_SUMMARY = "messages_under_summary",
  MESSAGE_WITH_BODIES = "message_with_bodies"
}

// 評価観点の列挙型
enum EvaluationCriteria {
  // 文書全体の評価観点
  RHETORICAL_EXPRESSION = "rhetorical_expression",  // 修辞表現の確認
  
  // サマリー全体の評価観点
  PREVIOUS_DISCUSSION_REVIEW = "previous_discussion_review",  // 前回討議の振り返りの有無
  SCQA_PRESENCE = "scqa_presence",  // SCQAの有無
  DUPLICATE_TRANSITION_CONJUNCTIONS = "duplicate_transition_conjunctions",  // 転換の接続詞の重複利用
  
  // サマリーペアの評価観点
  CONJUNCTION_VALIDITY = "conjunction_validity",  // 前のサマリー文を踏まえたときの、接続詞の妥当性
  INAPPROPRIATE_CONJUNCTIONS = "inappropriate_conjunctions",  // サマリー文に不適切な接続詞の有無
  LOGICAL_CONSISTENCY_WITH_PREVIOUS = "logical_consistency_with_previous",  // 直前のサマリーとの論理的整合性
  
  // サマリーとメッセージの評価観点
  SEQUENTIAL_DEVELOPMENT = "sequential_development",  // 逐次的展開の評価
  
  // メッセージ群の評価観点
  CONJUNCTION_APPROPRIATENESS = "conjunction_appropriateness",  // 接続詞の適切性
  DUPLICATE_TRANSITION_WORDS = "duplicate_transition_words",  // 転換の接続詞の二重利用
  AVOID_UNNECESSARY_NUMBERING = "avoid_unnecessary_numbering",  // 無駄なナンバリングの回避
  
  // メッセージとボディの評価観点
  MESSAGE_BODY_CONSISTENCY = "message_body_consistency"  // メッセージとボディの論理的整合性
}

// 評価結果のインターフェース
interface CriteriaResult {
  criteria: EvaluationCriteria;
  has_issues: boolean;
  issues: string;
}

interface EvaluationResult {
  target_text: string;
  scope: EvaluationScope;
  criteria_results: CriteriaResult[];
}

interface EvaluationResponse {
  status: string;
  message: string;
  results: EvaluationResult[];
  score: number;  // 評価スコア（0-100）
}

// ログを出力する関数
function log(message: string, type: 'info' | 'error' | 'success' | 'debug' = 'info') {
  // 現在の時刻を取得
  const now = new Date();
  const timeString = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
  
  // コンソールに出力
  switch (type) {
    case 'error':
      console.error(`[${timeString}] ${message}`);
      break;
    case 'success':
      console.log(`[${timeString}] ✓ ${message}`);
      break;
    case 'debug':
      console.debug(`[${timeString}] ${message}`);
      break;
    case 'info':
    default:
      console.log(`[${timeString}] ${message}`);
      break;
  }
}

// Office.jsの初期化
Office.onReady((info) => {
  if (info.host === Office.HostType.Word) {
    document.getElementById("app-body").style.display = "flex";
    document.getElementById("sideload-msg").style.display = "none";

    // 実行ボタンのイベントリスナーを設定
    document.getElementById("run").addEventListener("click", run);

    // スコープボタンのイベントリスナーを設定
    setupScopeButtons();

    // すべて表示ボタンのイベントリスナーを設定
    const showAllButton = document.getElementById("show-all");
    if (showAllButton) {
      showAllButton.addEventListener("click", async () => {
        log("すべてのコメントを表示します", 'info');
        
        // アクティブなスコープをクリア
        document.querySelectorAll('.scope-button').forEach(btn => {
          btn.classList.remove('active');
        });
        
        // すべてのコメントを表示
        await showAllComments();
      });
    }

    log("アプリケーションが初期化されました", 'info');
  }
});

// テキスト範囲にコメントを安全に追加する関数
async function addCommentSafely(context: Word.RequestContext, range: Word.Range, commentText: string): Promise<boolean> {
  try {
    // コメントを追加
    range.insertComment(commentText);
    await context.sync();
    return true;
  } catch (error) {
    // コメント追加に失敗した場合はエラーをログに記録
    log(`コメント追加エラー: ${error.message}`, 'error');
    return false;
  }
}

// 文書内でテキストを検索する関数
async function findTextInDocument(context: Word.RequestContext, searchText: string, paragraphs: Word.ParagraphCollection): Promise<Word.Range | null> {
  // 検索テキストが空の場合はnullを返す
  if (!searchText || searchText.trim() === "") {
    log("検索テキストが空です", 'error');
      return null;
    }
    
  // 検索テキストが長すぎる場合は短くする
  const maxSearchLength = 255;
  let effectiveSearchText = searchText;
  if (searchText.length > maxSearchLength) {
    effectiveSearchText = searchText.substring(0, maxSearchLength);
    log(`検索テキストが長すぎるため、最初の${maxSearchLength}文字で検索します`, 'info');
  }
  
  try {
    // 完全一致で検索
    for (let i = 0; i < paragraphs.items.length; i++) {
      const paragraph = paragraphs.items[i];
      if (paragraph.text.includes(effectiveSearchText)) {
        // 段落内で検索テキストの位置を特定
        const startIndex = paragraph.text.indexOf(effectiveSearchText);
        const range = paragraph.getRange();
        
        // 検索テキストの範囲を取得（Word APIでは単一の引数を使用）
        return range;
      }
    }
    
    // 完全一致が見つからない場合は、部分一致で検索
    // 検索テキストを単語に分割
    const words = effectiveSearchText.split(/\s+/).filter(word => word.length > 3);
    
    if (words.length > 0) {
      // 最も長い単語を使用
      const longestWord = words.reduce((a, b) => a.length > b.length ? a : b);
      
      for (let i = 0; i < paragraphs.items.length; i++) {
        const paragraph = paragraphs.items[i];
        if (paragraph.text.includes(longestWord)) {
          log(`部分一致: "${longestWord}" を含む段落を見つけました`, 'debug');
          return paragraph.getRange();
        }
      }
    }
    
    // それでも見つからない場合は、最初の数文字で検索
    if (effectiveSearchText.length > 10) {
      const prefix = effectiveSearchText.substring(0, 10);
      
      for (let i = 0; i < paragraphs.items.length; i++) {
        const paragraph = paragraphs.items[i];
        if (paragraph.text.includes(prefix)) {
          log(`プレフィックス一致: "${prefix}" を含む段落を見つけました`, 'debug');
          return paragraph.getRange();
        }
      }
    }
    
    log(`テキスト "${effectiveSearchText.substring(0, 30)}..." が見つかりませんでした`, 'error');
    return null;
  } catch (error) {
    log(`テキスト検索エラー: ${error.message}`, 'error');
    return null;
  }
}

// テキストからキーワードを抽出する関数
function extractKeywords(text: string): string[] {
  // 単語に分割
  const words = text.split(/\s+/);
  
  // 短い単語や一般的な単語を除外
  const filteredWords = words.filter(word => {
    // 3文字未満の単語を除外
    if (word.length < 3) return false;
    
    // 一般的な単語や助詞、助動詞などを除外（日本語対応）
    const commonWords = ['これ', 'それ', 'あれ', 'この', 'その', 'あの', 'ます', 'です', 'した', 'ある', 'いる', 'れる', 'られる', 'など', 'ため', 'よう'];
    if (commonWords.includes(word)) return false;
    
    return true;
  });
  
  // 重複を除去して返す（TypeScriptエラーを修正）
  return Array.from(new Set(filteredWords));
}

// グローバル変数として評価結果を保持
let evaluationResults: EvaluationResult[] = [];
let activeScope: EvaluationScope | null = null;
let commentRanges: { [key: string]: Word.Range } = {};
let lastCheckResults: EvaluationResponse | null = null; // チェック実行結果を保存する変数

export async function run() {
  console.log("チェック実行を開始します");
  try {
    await Word.run(async (context) => {
      // ドキュメントの読み込み
      const documentBody = context.document.body;
      documentBody.load("text");
      
      // タイトルの取得（最初の段落を仮定）
      const titleParagraph = context.document.body.paragraphs.getFirst();
      titleParagraph.load("text");
      
      await context.sync();
      
      // デバッグ情報
      let debugInfo = `ドキュメント全体の文字数: ${documentBody.text.length}\n`;
      debugInfo += `最初の段落: ${titleParagraph.text}\n`;
      console.log("デバッグ情報:", debugInfo);
      
      try {
        // ログ表示
        log("ドキュメントの解析を開始します");
        
        // 箇条書きデータの構築
        const bulletPointsData = await buildBulletPointsData(context, titleParagraph.text);
        
        // 箇条書きデータが存在する場合
        if (bulletPointsData && bulletPointsData.summaries.length > 0) {
          // データの概要をログに出力
          const summariesCount = bulletPointsData.summaries.length;
          const messagesCount = bulletPointsData.summaries.reduce((count, summary) => count + summary.messages.length, 0);
          const bodiesCount = bulletPointsData.summaries.reduce((count, summary) => 
            count + summary.messages.reduce((mCount, message) => mCount + message.bodies.length, 0), 0);
          
          log(`解析結果: ${summariesCount}個のサマリー, ${messagesCount}個のメッセージ, ${bodiesCount}個のボディを検出`);
          
          try {
            // APIリクエストの準備
            const apiUrl = (document.getElementById("api-url") as HTMLInputElement).value;
            log(`APIリクエスト送信: ${apiUrl}`);
            
            const startTime = new Date().getTime();
            
            // APIリクエスト送信
            const response = await fetch(apiUrl, {
              method: "POST",
              headers: {
                "Content-Type": "application/json"
              },
              body: JSON.stringify(bulletPointsData)
            });
            
            const endTime = new Date().getTime();
            
            // レスポンスのステータスコードをチェック
            if (!response.ok) {
              const errorText = await response.text();
              log(`APIリクエストエラー: ${response.status} ${response.statusText}`, 'error');
              log(`エラー詳細: ${errorText}`, 'error');
              throw new Error(`APIリクエストエラー: ${response.status} ${response.statusText}`);
            }
            
            const responseData: EvaluationResponse = await response.json();
            
            // APIレスポンスをログに出力
            log(`APIレスポンス受信: ${endTime - startTime}ms`, 'success');
            log(`ステータス: ${responseData.status}, メッセージ: ${responseData.message}`);
            
            // APIレスポンスの詳細をコンソールに出力
            console.log("APIレスポンスの詳細:");
            console.log(responseData);
            console.log("評価結果:");
            console.log(responseData.results);
            console.log("スコア:", responseData.score);
            
            // チェック実行結果を保存
            lastCheckResults = responseData;
            
            // スコアを表示（バックエンドから受け取ったスコアを使用、未定義の場合は100）
            let score = 100; // デフォルト値
            if (responseData.score !== undefined && responseData.score !== null) {
              score = responseData.score;
              console.log("バックエンドから受け取ったスコア:", score);
            } else {
              console.log("スコアが未定義のためデフォルト値を使用:", score);
            }
            
            // スコアの型変換を確実に行う
            score = Number(score);
            if (isNaN(score)) {
              console.log("スコアが数値に変換できないためデフォルト値を使用");
              score = 100;
            }
            
            console.log("最終的に表示するスコア:", score);
            updateScore(score);
            
            // 評価結果の概要をログに出力
            const resultsWithIssues = responseData.results.filter(r => 
              r.criteria_results.some(cr => cr.has_issues)
            );
            log(`評価結果: ${responseData.results.length}件中${resultsWithIssues.length}件に問題あり`);
            log(`評価スコア: ${score}点`);
            
            // 評価結果をグローバル変数に保存
            evaluationResults = responseData.results;
            
            // スコープごとの状態を更新
            updateScopeStatus(evaluationResults);
            
            // 問題がある場合は詳細をログに出力
            if (resultsWithIssues.length > 0) {
              resultsWithIssues.forEach(result => {
                const issuesCriteria = result.criteria_results.filter(cr => cr.has_issues);
                if (issuesCriteria.length > 0) {
                  const targetPreview = result.target_text.length > 30 ? 
                    result.target_text.substring(0, 30) + "..." : result.target_text;
                  log(`問題あり: "${targetPreview}" (${issuesCriteria.length}個の評価観点で問題検出)`, 'error');
                }
              });
            }
            
            // 評価結果をWord文書に反映
            if (responseData.status === "success") {
              log("Word文書内でテキストを検索しています...");
              
              try {
                // 文書内のすべての段落を検索対象にする
                const allParagraphs = context.document.body.paragraphs;
                allParagraphs.load(["text", "font"]);
                await context.sync();
                
                // コメントをすべて削除
                await removeAllComments(context);
                
                // 優先順位が最も高いNGカテゴリーのコメントのみを表示
                await showHighestPriorityComments();
                
                // スコープボタンのイベントリスナーを設定
                setupScopeButtons();
                
                log("Word文書の更新が完了しました", 'success');
              } catch (error) {
                log(`Word文書更新エラー: ${error.message}`, 'error');
              }
            }
          } catch (error) {
            // エラーメッセージを表示
            log(`APIリクエストエラー: ${error.message || 'Unknown error'}`, 'error');
            
            // エラーの詳細情報を表示（利用可能な場合）
            if (error.stack) {
              log(`エラー詳細: ${error.stack}`, 'error');
            }
          }
        } else {
          // 箇条書きが見つからなかった場合
          log("箇条書きが見つかりませんでした", 'error');
        }
      } catch (error) {
        // Word APIエラーを表示
        log(`Word APIエラー: ${error.message}`, 'error');
      }

    await context.sync();
  });
  } catch (error) {
    // 全体的なエラーを表示
    log(`実行時エラー: ${error.message}`, 'error');
  }
}

// スコアを更新する関数
function updateScore(score: number) {
  const scoreDisplay = document.getElementById("score-display");
  const scoreMessage = document.getElementById("score-message");
  
  if (scoreDisplay && scoreMessage) {
    // スコアが未定義または無効な場合は100として扱う
    if (score === undefined || score === null || isNaN(score)) {
      log("スコアが未定義または無効です。デフォルト値を使用します。", 'error');
      score = 100;
    }
    
    // 整数値に変換
    score = Math.round(score);
    
    // スコアを表示
    scoreDisplay.textContent = `${score}`;
    console.log("スコア表示を更新:", score);
    
    // スコアに応じたメッセージと色を設定
    if (score >= 90) {
      scoreMessage.textContent = "素晴らしい！ほとんど問題がありません。";
      scoreDisplay.style.color = "#107C10"; // 緑色
    } else if (score >= 70) {
      scoreMessage.textContent = "良好です。いくつかの改善点があります。";
      scoreDisplay.style.color = "#0078D4"; // 青色
    } else if (score >= 50) {
      scoreMessage.textContent = "改善の余地があります。";
      scoreDisplay.style.color = "#FF8C00"; // オレンジ色
    } else if (score >= 30) {
      scoreMessage.textContent = "多くの問題点があります。修正が必要です。";
      scoreDisplay.style.color = "#E81123"; // 赤色
    } else {
      scoreMessage.textContent = "非常に多くの問題があります。大幅な修正が必要です。";
      scoreDisplay.style.color = "#A80000"; // 濃い赤色
    }
  }
}

// スコープごとの状態を更新する関数
function updateScopeStatus(results: EvaluationResult[]) {
  // 各スコープの問題の有無を確認
  const scopeHasIssues: { [key: string]: boolean } = {
    [EvaluationScope.DOCUMENT_WIDE]: false,
    [EvaluationScope.ALL_SUMMARIES]: false,
    [EvaluationScope.SUMMARY_PAIRS]: false,
    [EvaluationScope.SUMMARY_WITH_MESSAGES]: false,
    [EvaluationScope.MESSAGES_UNDER_SUMMARY]: false,
    [EvaluationScope.MESSAGE_WITH_BODIES]: false
  };
  
  // 評価結果からスコープごとの問題の有無を確認
  for (const result of results) {
    if (result.criteria_results.some(cr => cr.has_issues)) {
      scopeHasIssues[result.scope] = true;
    }
  }
  
  // 各スコープの状態を更新
  for (const scope in scopeHasIssues) {
    const statusElement = document.getElementById(`${scope}-status`);
    if (statusElement) {
      if (scopeHasIssues[scope]) {
        statusElement.textContent = "NG";
        statusElement.className = "label-ng";
      } else {
        statusElement.textContent = "OK";
        statusElement.className = "label-ok";
      }
    }
  }
}

// スコープボタンのイベントリスナーを設定する関数
function setupScopeButtons() {
  const scopeButtons = document.querySelectorAll('.scope-button');
  
  scopeButtons.forEach(button => {
    button.addEventListener('click', async () => {
      const scopeAttr = button.getAttribute('data-scope');
      if (scopeAttr) {
        log(`スコープ ${scopeAttr} がクリックされました`, 'info');
        
        // 文字列からEvaluationScopeに変換
        let scope: EvaluationScope;
        
        // スコープ文字列を適切なEnum値に変換
        switch (scopeAttr) {
          case "DOCUMENT_WIDE":
            scope = EvaluationScope.DOCUMENT_WIDE;
            break;
          case "ALL_SUMMARIES":
            scope = EvaluationScope.ALL_SUMMARIES;
            break;
          case "SUMMARY_PAIRS":
            scope = EvaluationScope.SUMMARY_PAIRS;
            break;
          case "SUMMARY_WITH_MESSAGES":
            scope = EvaluationScope.SUMMARY_WITH_MESSAGES;
            break;
          case "MESSAGES_UNDER_SUMMARY":
            scope = EvaluationScope.MESSAGES_UNDER_SUMMARY;
            break;
          case "MESSAGE_WITH_BODIES":
            scope = EvaluationScope.MESSAGE_WITH_BODIES;
            break;
          default:
            log(`不明なスコープ: ${scopeAttr}`, 'error');
            return;
        }
        
        console.log(`変換後のスコープ: ${scope}, 型: ${typeof scope}`);
        
        // アクティブなスコープを更新
        document.querySelectorAll('.scope-button').forEach(btn => {
          btn.classList.remove('active');
        });
        button.classList.add('active');
        
        // 選択されたスコープのコメントのみを表示
        await filterCommentsByScope(scope);
      }
    });
  });
  
  // すべて表示ボタンのイベントリスナーを設定
  const showAllButton = document.getElementById("show-all");
  if (showAllButton) {
    showAllButton.addEventListener("click", async () => {
      log("すべてのコメントを表示します", 'info');
      
      // アクティブなスコープをクリア
      document.querySelectorAll('.scope-button').forEach(btn => {
        btn.classList.remove('active');
      });
      
      // すべてのコメントを表示
      await showAllComments();
    });
  }
}

// すべてのコメントを表示する関数
async function showAllComments() {
  if (!evaluationResults || evaluationResults.length === 0) {
    log("評価結果がありません。先にチェックを実行してください。", 'error');
    return;
  }

  log("すべてのコメントを表示します", 'info');
  console.log("表示する評価結果:", evaluationResults);
  
  await Word.run(async (context) => {
    try {
      // すべてのコメントを削除
      await removeAllComments(context);
      
      // 評価結果からコメントを再作成
      const allParagraphs = context.document.body.paragraphs;
      allParagraphs.load(["text", "font"]);
      await context.sync();
      
      // 問題がある評価結果のみをフィルタリング
      const resultsWithIssues = evaluationResults.filter(result => 
        result.criteria_results.some(cr => cr.has_issues)
      );
      
      console.log("問題がある評価結果:", resultsWithIssues);
      
      log(`問題がある評価結果は ${resultsWithIssues.length} 件あります`, 'info');
      
      if (resultsWithIssues.length === 0) {
        log("問題がある評価結果はありません", 'info');
        return;
      }
      
      // コメント範囲を保存するオブジェクトをクリア
      commentRanges = {};
      
      // 各評価結果に対してコメントを追加
      for (const result of resultsWithIssues) {
        const issuesCriteria = result.criteria_results.filter(cr => cr.has_issues);
        
        // 特別なケース: ALL_SUMMARIESスコープでタイトルに関連する場合
        if (result.scope === EvaluationScope.ALL_SUMMARIES && result.target_text === document.title) {
          const titleParagraph = context.document.body.paragraphs.getFirst();
          titleParagraph.load("text");
          await context.sync();
          
          // タイトルをハイライト
          titleParagraph.font.highlightColor = "yellow";
          
          // コメントテキストを作成
          const commentText = `【${getScopeName(result.scope)}】\n` + issuesCriteria.map(cr => 
            `【${getCriteriaName(cr.criteria)}】: ${cr.issues}`
          ).join('\n\n');
          
          // コメント追加
          const commentAdded = await addCommentSafely(context, titleParagraph.getRange(), commentText);
          if (commentAdded) {
            // コメント範囲を保存
            commentRanges[`${result.scope}_${issuesCriteria[0].criteria}`] = titleParagraph.getRange();
          }
          continue;
        }
        
        // 通常のケース: テキストを検索してコメントを追加
        const matchedRange = await findTextInDocument(context, result.target_text, allParagraphs);
        
        if (matchedRange) {
          // ハイライト
          matchedRange.font.highlightColor = "yellow";
          
          // コメントテキストを作成（スコープ名を含める）
          const commentText = `【${getScopeName(result.scope)}】\n` + issuesCriteria.map(cr => 
            `【${getCriteriaName(cr.criteria)}】: ${cr.issues}`
          ).join('\n\n');
          
          // コメント追加
          const commentAdded = await addCommentSafely(context, matchedRange, commentText);
          if (commentAdded) {
            log(`"${result.target_text.substring(0, 30)}..." にコメントを追加しました`, 'success');
            // コメント範囲を保存
            commentRanges[`${result.scope}_${issuesCriteria[0].criteria}`] = matchedRange;
          }
        } else {
          log(`"${result.target_text.substring(0, 30)}..." が見つかりませんでした`, 'error');
        }
      }
      
      await context.sync();
      log("すべてのコメントを表示しました", 'success');
    } catch (error) {
      log(`コメント表示エラー: ${error.message}`, 'error');
    }
  });
}

// スコープに基づいてコメントをフィルタリングする関数
async function filterCommentsByScope(scope: EvaluationScope) {
  if (!evaluationResults || evaluationResults.length === 0) {
    log("評価結果がありません。先にチェックを実行してください。", 'error');
    return;
  }

  log(`スコープ ${getScopeName(scope)} のコメントをフィルタリングします`, 'info');
  console.log(`フィルタリング対象のスコープ:`, scope);
  
  await Word.run(async (context) => {
    try {
      // すべてのコメントを削除
      await removeAllComments(context);
      
      // 選択したスコープのコメントのみを再表示
      const allParagraphs = context.document.body.paragraphs;
      allParagraphs.load(["text", "font"]);
      await context.sync();
      
      // 選択したスコープに関連する評価結果をフィルタリング
      const filteredResults = evaluationResults.filter(result => {
        // スコープの比較（文字列の場合とEnum値の場合の両方に対応）
        const resultScope = result.scope;
        const isMatchingScope = 
          resultScope === scope || 
          resultScope === scope.toString() || 
          resultScope.toString() === scope.toString();
        
        return isMatchingScope && result.criteria_results.some(cr => cr.has_issues);
      });
      
      // フィルタリング結果をコンソールに出力
      console.log("全評価結果:", evaluationResults);
      console.log(`スコープ ${scope} でフィルタリングした結果:`, filteredResults);
      console.log("フィルタリング条件:", `result.scope === ${scope} または文字列比較`);
      
      // 各評価結果のスコープを確認
      console.log("各評価結果のスコープ:");
      evaluationResults.forEach((result, index) => {
        console.log(`結果 ${index}: スコープ = ${result.scope}, 型 = ${typeof result.scope}`);
      });
      
      log(`スコープ ${getScopeName(scope)} に関連する問題は ${filteredResults.length} 件あります`, 'info');
      
      if (filteredResults.length === 0) {
        log(`スコープ ${getScopeName(scope)} に関連する問題はありません`, 'info');
        return;
      }
      
      // コメント範囲を保存するオブジェクトをクリア
      commentRanges = {};
      
      // 各評価結果に対してコメントを追加
      for (const result of filteredResults) {
        const issuesCriteria = result.criteria_results.filter(cr => cr.has_issues);
        
        // 特別なケース: ALL_SUMMARIESスコープでタイトルに関連する場合
        if (scope === EvaluationScope.ALL_SUMMARIES && result.target_text === document.title) {
          const titleParagraph = context.document.body.paragraphs.getFirst();
          titleParagraph.load("text");
          await context.sync();
          
          // タイトルをハイライト
          titleParagraph.font.highlightColor = "yellow";
          
          // コメントテキストを作成
          const commentText = `【${getScopeName(scope)}】\n` + issuesCriteria.map(cr => 
            `【${getCriteriaName(cr.criteria)}】: ${cr.issues}`
          ).join('\n\n');
          
          // コメント追加
          const commentAdded = await addCommentSafely(context, titleParagraph.getRange(), commentText);
          if (commentAdded) {
            // コメント範囲を保存
            commentRanges[`${result.scope}_${issuesCriteria[0].criteria}`] = titleParagraph.getRange();
          }
          continue;
        }
        
        // 通常のケース: テキストを検索してコメントを追加
        const matchedRange = await findTextInDocument(context, result.target_text, allParagraphs);
        
        if (matchedRange) {
          // ハイライト
          matchedRange.font.highlightColor = "yellow";
          
          // コメントテキストを作成（スコープ名を含める）
          const commentText = `【${getScopeName(scope)}】\n` + issuesCriteria.map(cr => 
            `【${getCriteriaName(cr.criteria)}】: ${cr.issues}`
          ).join('\n\n');
          
          // コメント追加
          const commentAdded = await addCommentSafely(context, matchedRange, commentText);
          if (commentAdded) {
            log(`"${result.target_text.substring(0, 30)}..." にコメントを追加しました`, 'success');
            // コメント範囲を保存
            commentRanges[`${result.scope}_${issuesCriteria[0].criteria}`] = matchedRange;
          }
        } else {
          log(`"${result.target_text.substring(0, 30)}..." が見つかりませんでした`, 'error');
        }
      }
      
      await context.sync();
      log(`${getScopeName(scope)}のコメントのみを表示しました`, 'success');
      
      // アクティブなスコープを更新
      activeScope = scope;
    } catch (error) {
      log(`コメントフィルタリングエラー: ${error.message}`, 'error');
    }
  });
}

// すべてのコメントを削除する関数
async function removeAllComments(context: Word.RequestContext) {
  try {
    // Word APIではコメントを直接削除する方法がないため、
    // 代わりにすべてのコメントを検索して削除する
    const searchResults = context.document.body.search("*", { matchWildcards: true });
    searchResults.load("text");
    await context.sync();
    
    // すべてのコメントを削除
    for (let i = 0; i < searchResults.items.length; i++) {
      const range = searchResults.items[i];
      const comments = range.getComments();
      comments.load("text");
      await context.sync();
      
      if (comments.items.length > 0) {
        for (let j = 0; j < comments.items.length; j++) {
          comments.items[j].delete();
        }
      }
    }
    
    await context.sync();
    log("すべてのコメントを削除しました", 'debug');
  } catch (error) {
    log(`コメント削除エラー: ${error.message}`, 'error');
  }
}

// 評価観点の名前を取得する
function getCriteriaName(criteria: EvaluationCriteria): string {
  const criteriaNames = {
    [EvaluationCriteria.RHETORICAL_EXPRESSION]: "修辞表現の確認",
    [EvaluationCriteria.PREVIOUS_DISCUSSION_REVIEW]: "前回討議の振り返りの有無",
    [EvaluationCriteria.SCQA_PRESENCE]: "SCQAの有無",
    [EvaluationCriteria.DUPLICATE_TRANSITION_CONJUNCTIONS]: "転換の接続詞の重複利用",
    [EvaluationCriteria.CONJUNCTION_VALIDITY]: "前のサマリー文を踏まえたときの、接続詞の妥当性",
    [EvaluationCriteria.INAPPROPRIATE_CONJUNCTIONS]: "サマリー文に不適切な接続詞の有無",
    [EvaluationCriteria.LOGICAL_CONSISTENCY_WITH_PREVIOUS]: "直前のサマリーとの論理的整合性",
    [EvaluationCriteria.SEQUENTIAL_DEVELOPMENT]: "逐次的展開の評価",
    [EvaluationCriteria.CONJUNCTION_APPROPRIATENESS]: "接続詞の適切性",
    [EvaluationCriteria.DUPLICATE_TRANSITION_WORDS]: "転換の接続詞の二重利用",
    [EvaluationCriteria.AVOID_UNNECESSARY_NUMBERING]: "無駄なナンバリングの回避",
    [EvaluationCriteria.MESSAGE_BODY_CONSISTENCY]: "メッセージとボディの論理的整合性"
  };
  
  return criteriaNames[criteria] || criteria;
}

// 評価範囲の名前を取得する
function getScopeName(scope: EvaluationScope): string {
  const scopeNames = {
    [EvaluationScope.DOCUMENT_WIDE]: "ドキュメント全体",
    [EvaluationScope.ALL_SUMMARIES]: "すべてのサマリー",
    [EvaluationScope.SUMMARY_PAIRS]: "サマリーペア",
    [EvaluationScope.SUMMARY_WITH_MESSAGES]: "サマリーとメッセージ",
    [EvaluationScope.MESSAGES_UNDER_SUMMARY]: "サマリー下のメッセージ",
    [EvaluationScope.MESSAGE_WITH_BODIES]: "メッセージと本文"
  };
  
  return scopeNames[scope] || scope;
}

// 箇条書きデータを構築する関数
async function buildBulletPointsData(context: Word.RequestContext, titleText: string): Promise<BulletPointsRequest | null> {
  // 段落の読み込み
        const paragraphs = context.document.body.paragraphs;
        paragraphs.load(["text", "font", "firstLineIndent", "leftIndent"]);
        await context.sync();
        
        log(`文書内の段落数: ${paragraphs.items.length}`);
        
        // 箇条書きの階層構造を格納するオブジェクト
        const bulletPointsData: BulletPointsRequest = {
    title: titleText,
          summaries: []
        };
        
        // 各段落を処理して箇条書きを検出
        const bulletPoints = [];

        for (let i = 0; i < paragraphs.items.length; i++) {
          const paragraph = paragraphs.items[i];
          const text = paragraph.text.trim();
          
          // 空の段落はスキップ
          if (!text) continue;
    
    // タイトルと同じ段落はスキップ
    if (text === titleText) continue;
          
          // 箇条書きの特徴を検出（テキストの先頭に記号があるか、インデントがあるか）
          const isBulletPoint = 
            text.startsWith("•") || 
            text.startsWith("-") || 
            text.startsWith("*") ||
            text.startsWith("○") ||
            text.startsWith("・") ||
            text.match(/^\d+[\.\)]\s/) ||  // 数字+ドットまたは括弧
            paragraph.leftIndent > 0 ||
            paragraph.firstLineIndent < 0;  // ぶら下げインデント
          
          if (isBulletPoint) {
            // インデントレベルに基づいて階層を推定
            let level = 0;
            
            if (paragraph.leftIndent > 0) {
              // インデント量に基づいてレベルを推定（72ポイント = 1インチ ≒ 1レベル）
              level = Math.min(2, Math.floor(paragraph.leftIndent / 24));
            }
            
            // 先頭の記号を削除してテキストをクリーンアップ
            let cleanText = text
              .replace(/^[•\-*○・]\s*/, '')  // 記号を削除
              .replace(/^\d+[\.\)]\s*/, '')  // 数字+ドットまたは括弧を削除
              .trim();
            
            bulletPoints.push({
              text: cleanText,
              level: level,
              paragraph: paragraph  // 段落オブジェクトを保持
            });
            
      log(`箇条書き検出: レベル ${level}, テキスト: ${cleanText.substring(0, 30)}...`, 'debug');
          }
        }
        
        log(`検出された箇条書き: ${bulletPoints.length}件`);
  
  // 箇条書きが見つからなかった場合
  if (bulletPoints.length === 0) {
    return null;
  }
        
        // 現在処理中のsummary, message, bodyを追跡する変数
        let currentSummary: Summary = null;
        let currentMessage: Message = null;
        
        // 各箇条書きを処理
        for (const bulletPoint of bulletPoints) {
          const level = bulletPoint.level;
          const text = bulletPoint.text;
          
          // 空の箇条書きはスキップ
          if (!text) continue;
          
          // 階層レベルに応じて処理
          if (level === 0) {
            // 第一階層 (summary)
            currentSummary = {
              content: text,
              messages: []
            };
            bulletPointsData.summaries.push(currentSummary);
            currentMessage = null;
          } else if (level === 1) {
            // 第二階層 (message)
            if (!currentSummary) {
              // 親のsummaryがない場合は作成
              currentSummary = {
                content: "未分類",
                messages: []
              };
              bulletPointsData.summaries.push(currentSummary);
            }
            
            currentMessage = {
              content: text,
              bodies: []
            };
            currentSummary.messages.push(currentMessage);
          } else if (level === 2) {
            // 第三階層 (body)
            if (!currentMessage) {
              // 親のmessageがない場合は作成
              if (!currentSummary) {
                currentSummary = {
                  content: "未分類",
                  messages: []
                };
                bulletPointsData.summaries.push(currentSummary);
              }
              
              currentMessage = {
                content: "未分類",
                bodies: []
              };
              currentSummary.messages.push(currentMessage);
            }
            
            currentMessage.bodies.push({
              content: text
            });
          }
        }
        
  // データの概要をログに出力
  const summariesCount = bulletPointsData.summaries.length;
  const messagesCount = bulletPointsData.summaries.reduce((count, summary) => count + summary.messages.length, 0);
  const bodiesCount = bulletPointsData.summaries.reduce((count, summary) => 
    count + summary.messages.reduce((mCount, message) => mCount + message.bodies.length, 0), 0);
  
  log(`構築結果: ${summariesCount}個のサマリー, ${messagesCount}個のメッセージ, ${bodiesCount}個のボディ`);
  
  // 箇条書きデータの構築が完了
  log(`箇条書きデータの構築が完了しました: ${bulletPointsData.summaries.length}個のサマリー`);
  
  // デバッグ用に箇条書きデータの内容をコンソールに出力
  console.log("構築された箇条書きデータ:", bulletPointsData);
  
  return bulletPointsData;
}

// 優先順位が最も高いNGカテゴリーのコメントのみを表示する関数
async function showHighestPriorityComments() {
  if (!evaluationResults || evaluationResults.length === 0) {
    log("評価結果がありません。先にチェックを実行してください。", 'error');
    return;
  }

  log("優先順位が最も高いNGカテゴリーのコメントを表示します", 'info');
  
  // スコープの優先順位を定義（インデックスが小さいほど優先順位が高い）
  const scopePriority = [
    EvaluationScope.DOCUMENT_WIDE,
    EvaluationScope.ALL_SUMMARIES,
    EvaluationScope.SUMMARY_PAIRS,
    EvaluationScope.SUMMARY_WITH_MESSAGES,
    EvaluationScope.MESSAGES_UNDER_SUMMARY,
    EvaluationScope.MESSAGE_WITH_BODIES
  ];
  
  // 各スコープに問題があるかどうかを確認
  const scopeHasIssues: { [key: string]: boolean } = {};
  for (const scope of scopePriority) {
    // スコープの比較（文字列の場合とEnum値の場合の両方に対応）
    scopeHasIssues[scope] = evaluationResults.some(result => {
      const resultScope = result.scope;
      const isMatchingScope = 
        resultScope === scope || 
        resultScope === scope.toString() || 
        resultScope.toString() === scope.toString();
      
      return isMatchingScope && result.criteria_results.some(cr => cr.has_issues);
    });
  }
  
  console.log("各スコープの問題の有無:", scopeHasIssues);
  
  // 優先順位が最も高いNGカテゴリーを特定
  let highestPriorityScope: EvaluationScope | null = null;
  for (const scope of scopePriority) {
    if (scopeHasIssues[scope]) {
      highestPriorityScope = scope;
      break;
    }
  }
  
  // 優先順位が最も高いNGカテゴリーが見つかった場合
  if (highestPriorityScope) {
    log(`優先順位が最も高いNGカテゴリー: ${getScopeName(highestPriorityScope)}`, 'info');
    
    // 該当するスコープのボタンをアクティブにする
    document.querySelectorAll('.scope-button').forEach(btn => {
      btn.classList.remove('active');
      const btnScope = btn.getAttribute('data-scope');
      if (btnScope && (
          btnScope === highestPriorityScope || 
          btnScope === highestPriorityScope.toString()
        )) {
        btn.classList.add('active');
      }
    });
    
    // 該当するスコープのコメントのみを表示
    await filterCommentsByScope(highestPriorityScope);
  } else {
    log("NGカテゴリーが見つかりませんでした。すべてのコメントを表示します。", 'info');
    await showAllComments();
  }
}

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
}

// シンプルなログ機能
function log(message: string, type: 'info' | 'error' | 'success' = 'info') {
  const logContainer = document.getElementById("log-container");
  if (!logContainer) return;
  
  const timestamp = new Date().toLocaleTimeString();
  const logEntry = document.createElement("div");
  logEntry.className = `log-entry log-${type}`;
  logEntry.innerHTML = `<span class="log-time">[${timestamp}]</span> ${message}`;
  
  // 最新のログを上に表示
  logContainer.insertBefore(logEntry, logContainer.firstChild);
  
  // ログが多すぎる場合は古いものを削除
  if (logContainer.children.length > 50) {
    logContainer.removeChild(logContainer.lastChild);
  }
}

Office.onReady((info) => {
  if (info.host === Office.HostType.Word) {
    document.getElementById("sideload-msg").style.display = "none";
    document.getElementById("app-body").style.display = "flex";
    document.getElementById("run").onclick = run;
  }
});

// コメント追加のヘルパー関数を追加
async function addCommentSafely(context, range, commentText) {
  // 処理開始のログ
  log('addCommentSafely: 処理を開始しました', 'debug');
  
  // コメントテキストの長さ制限に使用する定数
  const maxCommentLength = 500;
  
  // 実際に使うコメントテキスト（長い場合は一部を省略）
  let safeCommentText = commentText;

  try {
    log(`addCommentSafely: コメントテキストの長さは ${commentText.length} 文字`, 'debug');

    // コメントテキストが長すぎる場合は制限する
    if (commentText.length > maxCommentLength) {
      safeCommentText = commentText.substring(0, maxCommentLength) + "...（省略）";
      log(`コメントが長すぎるため ${maxCommentLength} 文字に制限しました`, 'info');
    }

    // 同期して状態を確実にする前にログ出力
    log('addCommentSafely: context.sync() を実行します', 'debug');
    await context.sync();
    log('addCommentSafely: context.sync() 完了', 'debug');

    // コメントを追加する前にログ出力
    log(`addCommentSafely: range.insertComment を実行します`, 'debug');
    range.insertComment(safeCommentText);

    // 同期して変更を適用
    log('addCommentSafely: コメント追加後に context.sync() を実行します', 'debug');
    await context.sync();
    log('addCommentSafely: コメント追加と同期が完了しました', 'debug');

    // 正常終了
    log('addCommentSafely: 処理が正常に終了しました', 'info');
    return true;
  } catch (error) {
    // どのようなエラーなのか、より詳しくログを出す
    log(`コメント追加エラー: ${error.message}`, 'error');
    log(`エラー名: ${error.name}`, 'error');
    if (error.stack) {
      log(`スタックトレース: ${error.stack}`, 'error');
    }

    // 必要に応じてエラー内容を再スローしたり、追加処理を行う
    // throw error;

    return false;
  }
}

// テキスト検索のヘルパー関数を追加
async function findTextInDocument(context: Word.RequestContext, searchText: string, allParagraphs: Word.ParagraphCollection = null): Promise<Word.Range | null> {
  try {
    log(`"${searchText.substring(0, 30)}${searchText.length > 30 ? '...' : ''}"を文書内で検索中...`);
    
    // 検索テキストが短すぎる場合は検索しない
    if (searchText.length < 3) {
      log(`検索テキストが短すぎます: "${searchText}"`);
      return null;
    }
    
    // 1. まず完全一致で段落を検索
    if (allParagraphs) {
      for (let i = 0; i < allParagraphs.items.length; i++) {
        const paragraph = allParagraphs.items[i];
        if (paragraph.text.trim() === searchText.trim()) {
          log(`完全一致する段落を発見: "${searchText.substring(0, 30)}..."`);
          return paragraph.getRange();
        }
      }
    }
    
    // 2. 部分一致で段落を検索
    if (allParagraphs) {
      for (let i = 0; i < allParagraphs.items.length; i++) {
        const paragraph = allParagraphs.items[i];
        if (paragraph.text.includes(searchText)) {
          log(`部分一致する段落を発見: "${searchText.substring(0, 30)}..."`);
          return paragraph.getRange();
        }
      }
    }
    
    // 3. 単語単位で検索（長いテキストの場合）
    if (searchText.length > 10) {
      // 最初の数単語だけを使用
      const words = searchText.split(' ');
      const shortSearchText = words.slice(0, Math.min(5, words.length)).join(' ');
      
      if (shortSearchText.length > 3) {
        log(`短縮テキストで検索: "${shortSearchText}"`);
        
        // 文書全体を取得
        const documentText = context.document.body.getRange();
        documentText.load("text");
        await context.sync();
        
        // 短縮テキストで検索
        const searchResults = documentText.search(shortSearchText);
        searchResults.load("text");
        await context.sync();
        
        log(`検索結果: ${searchResults.items.length}件`);
        
        if (searchResults.items.length > 0) {
          log(`部分一致するテキストを発見: "${shortSearchText}"`);
          return searchResults.items[0];
        }
      }
    }
    
    // 4. キーワード検索（最後の手段）
    // 重要そうな単語を抽出して検索
    const keywords = extractKeywords(searchText);
    log(`キーワード検索: ${keywords.join(', ')}`);
    
    for (const keyword of keywords) {
      if (keyword.length > 3) {
        // 文書全体を取得
        const documentText = context.document.body.getRange();
        documentText.load("text");
        await context.sync();
        
        // キーワードで検索
        const searchResults = documentText.search(keyword);
        searchResults.load("text");
        await context.sync();
        
        log(`キーワード "${keyword}" の検索結果: ${searchResults.items.length}件`);
        
        if (searchResults.items.length > 0) {
          log(`キーワード "${keyword}" に一致するテキストを発見`);
          return searchResults.items[0];
        }
      }
    }
    
    log(`"${searchText.substring(0, 30)}..."に一致するテキストが見つかりませんでした`, 'error');
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

export async function run() {
  try {
  return Word.run(async (context) => {
      // 結果表示エリアをリセット
      const resultContainer = document.getElementById("result-container");
      const resultElement = document.getElementById("result");
      resultContainer.style.display = "none";
      resultElement.textContent = "";

      // デバッグ情報を表示するための変数
      let debugInfo = "";

      try {
        // 処理開始をログに記録
        log("箇条書き評価処理を開始します");
        
        // 代替アプローチ: 段落のインデントレベルを使用して箇条書きを検出
        const paragraphs = context.document.body.paragraphs;
        paragraphs.load(["text", "font", "firstLineIndent", "leftIndent"]);
        await context.sync();
        
        debugInfo += `段落の総数: ${paragraphs.items.length}\n`;
        log(`文書内の段落数: ${paragraphs.items.length}`);
        
        // 箇条書きの階層構造を格納するオブジェクト
        const bulletPointsData: BulletPointsRequest = {
          summaries: []
        };
        
        // 各段落を処理して箇条書きを検出
        const bulletPoints = [];
        
        // タイトルを検出（最初の非箇条書きテキスト）
        let titleParagraph = null;
        let titleText = "";

        for (let i = 0; i < paragraphs.items.length; i++) {
          const paragraph = paragraphs.items[i];
          const text = paragraph.text.trim();
          
          // 空の段落はスキップ
          if (!text) continue;
          
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
          
          if (!isBulletPoint && titleParagraph === null) {
            // 最初の非箇条書きテキストをタイトルとして保存
            titleParagraph = paragraph;
            titleText = text;
            log(`タイトルを検出しました: ${text}`);
            // タイトルをリクエストに追加
            bulletPointsData.title = text;
            continue; // タイトルはサマリーとして扱わない
          }
          
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
            
            debugInfo += `箇条書き検出: レベル ${level}, テキスト: ${cleanText}\n`;
          }
        }
        
        debugInfo += `検出された箇条書きの数: ${bulletPoints.length}\n`;
        log(`検出された箇条書き: ${bulletPoints.length}件`);
        
        // 現在処理中のsummary, message, bodyを追跡する変数
        let currentSummary: Summary = null;
        let currentMessage: Message = null;
        
        // 段落オブジェクトとサマリーの対応を記録
        const summaryParagraphs = new Map();
        
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
            
            // サマリーと段落オブジェクトの対応を記録
            summaryParagraphs.set(text, bulletPoint.paragraph);
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
        
        // データをバックエンドに送信
        if (bulletPointsData.summaries.length > 0) {
          const apiUrl = (document.getElementById("api-url") as HTMLInputElement).value;
          
          log(`APIリクエスト送信: ${apiUrl}`);
          log(`サマリー数: ${bulletPointsData.summaries.length}件`);
          
          try {
            const startTime = new Date().getTime();
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
            
            // 評価結果の概要をログに出力
            const resultsWithIssues = responseData.results.filter(r => 
              r.criteria_results.some(cr => cr.has_issues)
            );
            log(`評価結果: ${responseData.results.length}件中${resultsWithIssues.length}件に問題あり`);
            
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
            
            // 結果を表示
            resultContainer.style.display = "block";
            resultElement.textContent = JSON.stringify(responseData, null, 2);
            
            // 評価結果をWord文書に反映
            if (responseData.status === "success") {
              log("Word文書内でテキストを検索しています...");
              
              try {
                // 文書内のすべての段落を検索対象にする
                const allParagraphs = context.document.body.paragraphs;
                allParagraphs.load(["text", "font"]);
                await context.sync();
                
                // 各評価結果を処理（まずはハイライトのみ適用）
                log("評価結果に基づいてテキストをハイライトしています...");
                for (const result of responseData.results) {
                  // 問題がある評価観点を抽出
                  const issuesCriteria = result.criteria_results.filter(cr => cr.has_issues);
                  
                  // 問題がある場合のみハイライトを追加
                  if (issuesCriteria.length > 0) {
                    try {
                      // ALL_SUMMARIESの評価結果はタイトルにハイライト
                      if (result.scope === EvaluationScope.ALL_SUMMARIES && titleParagraph) {
                        log(`ALL_SUMMARIESの評価結果をタイトルにハイライトします`);
                        
                        // タイトルをハイライト
                        titleParagraph.font.highlightColor = "yellow";
                      }
                      // DOCUMENT_WIDEの評価範囲の場合
                      else if (result.scope === EvaluationScope.DOCUMENT_WIDE) {
                        // 改善された検索関数を使用
                        const matchedRange = await findTextInDocument(context, result.target_text, allParagraphs);
                        
                        if (matchedRange) {
                          // ハイライト
                          matchedRange.font.highlightColor = "yellow";
                          await context.sync();
                        }
                      }
                      // その他の評価範囲の場合
                      else {
                        // 改善された検索関数を使用
                        const matchedRange = await findTextInDocument(context, result.target_text, allParagraphs);
                        
                        if (matchedRange) {
                          // ハイライト
                          matchedRange.font.highlightColor = "yellow";
                          await context.sync();
                        }
                      }
                    } catch (error) {
                      log(`ハイライト処理エラー: ${error.message}`, 'error');
                    }
                  }
                }
                
                // 変更を同期
                await context.sync();
                log("ハイライト処理が完了しました", 'success');
                
                // コメント追加処理を分離して実行
                log("評価結果に基づいてコメントを追加しています...");
                
                // 各評価結果を処理（コメント追加）
                for (const result of responseData.results) {
                  // 問題がある評価観点を抽出
                  const issuesCriteria = result.criteria_results.filter(cr => cr.has_issues);
                  
                  // 問題がある場合のみコメントを追加
                  if (issuesCriteria.length > 0) {
                    try {
                      const matchedRange = await findTextInDocument(context, result.target_text, allParagraphs);

                      
                      if (matchedRange) {
                        // 問題点をまとめたコメントを作成
                        const commentText = `【${getScopeName(result.scope)}】\n` + 
                          issuesCriteria.map(cr => 
                            `【${getCriteriaName(cr.criteria)}】: ${cr.issues}`
                          ).join('\n\n');
                        
                        // コメント追加を試みる（失敗してもエラーにしない）
                        const commentAdded = await addCommentSafely(context, matchedRange, commentText);
                        
                        if (commentAdded) {
                          log(`評価結果をテキストに追加しました: ${getCriteriaName(issuesCriteria[0].criteria)}`, 'success');
                        } else {
                          // コメント追加に失敗した場合はテキスト色を変更
                          matchedRange.font.color = "red";
                          await context.sync();
                          log(`コメント追加に失敗したため、テキスト色を変更しました`, 'error');
                        }
                      }
                      // }
                    } catch (error) {
                      log(`コメント処理エラー: ${error.message}`, 'error');
                    }
                  }
                }
                
                // 変更を同期
                await context.sync();
                log("コメント追加処理が完了しました", 'success');
                
                
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
            
            // 結果表示エリアにエラーメッセージを表示
            resultContainer.style.display = "block";
            resultElement.textContent = `エラーが発生しました: ${error.message || 'Unknown error'}`;
          }
        } else {
          // 箇条書きが見つからなかった場合
          log("箇条書きが見つかりませんでした", 'error');
          resultContainer.style.display = "block";
          resultElement.textContent = `箇条書きが見つかりませんでした。\n\nデバッグ情報:\n${debugInfo}`;
        }
      } catch (error) {
        // Word APIエラーを表示
        log(`Word APIエラー: ${error.message}`, 'error');
        resultContainer.style.display = "block";
        resultElement.textContent = `Word API エラー: ${error.message}\n\nデバッグ情報:\n${debugInfo}`;
      }

    await context.sync();
  });
  } catch (error) {
    // 全体的なエラーを表示
    log(`実行時エラー: ${error.message}`, 'error');
    const resultContainer = document.getElementById("result-container");
    const resultElement = document.getElementById("result");
    resultContainer.style.display = "block";
    resultElement.textContent = `実行時エラー: ${error.message}`;
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
    [EvaluationScope.DOCUMENT_WIDE]: "文書全体",
    [EvaluationScope.ALL_SUMMARIES]: "サマリー全体",
    [EvaluationScope.SUMMARY_PAIRS]: "サマリー内の文のペア",
    [EvaluationScope.SUMMARY_WITH_MESSAGES]: "サマリーとメッセージ",
    [EvaluationScope.MESSAGES_UNDER_SUMMARY]: "サマリー配下のメッセージ群",
    [EvaluationScope.MESSAGE_WITH_BODIES]: "メッセージとボディ"
  };
  
  return scopeNames[scope] || scope;
}

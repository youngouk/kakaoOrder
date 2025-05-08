import React, { useState, useEffect, useCallback } from 'react';
import * as XLSX from 'xlsx';

function ResultDisplay({ analysisData, isLoading, shopName }) {
  const [activeTab, setActiveTab] = useState('time');
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredData, setFilteredData] = useState({
    available_products: [],
    time_based_orders: [],
    item_based_summary: [],
    customer_based_orders: [],
    table_summary: {
      headers: [],
      rows: [],
      required_quantities: []
    },
    order_pattern_analysis: {
      peak_hours: [],
      popular_items: [],
      sold_out_items: []
    },
    shop_name: ''
  });

  // 안전한 초기화를 위해 분석 데이터 검증
  useEffect(() => {
    if (!analysisData) return;
    
    // 빈 배열이나 undefined일 경우를 처리
    const safeData = {
      available_products: Array.isArray(analysisData.available_products) ? analysisData.available_products : [],
      time_based_orders: Array.isArray(analysisData.time_based_orders) ? analysisData.time_based_orders : [],
      item_based_summary: Array.isArray(analysisData.item_based_summary) ? analysisData.item_based_summary : [],
      customer_based_orders: Array.isArray(analysisData.customer_based_orders) ? analysisData.customer_based_orders : [],
      table_summary: analysisData.table_summary || {
        headers: [],
        rows: [],
        required_quantities: []
      }
    };
    
    setFilteredData(safeData);
  }, [analysisData]);

  // 검색어에 따라 데이터 필터링
  useEffect(() => {
    if (!analysisData) return;
    
    // 안전한 참조를 위해 데이터 확인
    const safeData = {
      available_products: Array.isArray(analysisData.available_products) ? analysisData.available_products : [],
      time_based_orders: Array.isArray(analysisData.time_based_orders) ? analysisData.time_based_orders : [],
      item_based_summary: Array.isArray(analysisData.item_based_summary) ? analysisData.item_based_summary : [],
      customer_based_orders: Array.isArray(analysisData.customer_based_orders) ? analysisData.customer_based_orders : [],
      table_summary: analysisData.table_summary || { headers: [], rows: [], required_quantities: [] }
    };
    
    const term = searchTerm.toLowerCase();
    if (!term) {
      setFilteredData(safeData);
      return;
    }

    // 판매 상품 필터링
    const filterAvailableProducts = () => {
      return safeData.available_products.filter(product => 
        product.name?.toLowerCase().includes(term) ||
        product.category?.toLowerCase().includes(term) ||
        product.price?.toString().toLowerCase().includes(term) ||
        product.delivery_date?.toLowerCase().includes(term)
      );
    };

    const filterTimeOrders = () => {
      return safeData.time_based_orders.filter(order => 
        order.time?.toLowerCase().includes(term) ||
        order.customer?.toLowerCase().includes(term) ||
        order.item?.toLowerCase().includes(term) ||
        order.quantity?.toString().toLowerCase().includes(term) ||
        order.note?.toLowerCase().includes(term)
      );
    };

    const filterItemSummary = () => {
      return safeData.item_based_summary.filter(item => 
        item.item?.toLowerCase().includes(term) ||
        item.total_quantity?.toString().toLowerCase().includes(term) ||
        item.customers?.toLowerCase().includes(term)
      );
    };

    const filterCustomerOrders = () => {
      return safeData.customer_based_orders.filter(order => 
        order.customer?.toLowerCase().includes(term) ||
        order.item?.toLowerCase().includes(term) ||
        order.quantity?.toString().toLowerCase().includes(term) ||
        order.note?.toLowerCase().includes(term)
      );
    };

    // 테이블 필터링 (고객 이름이나 상품명에 검색어가 포함된 경우 표시)
    const filterTableSummary = () => {
      if (!safeData.table_summary || !Array.isArray(safeData.table_summary.rows) || 
          !Array.isArray(safeData.table_summary.headers)) {
        return { headers: [], rows: [], required_quantities: [] };
      }

      const filteredRows = safeData.table_summary.rows.filter(row => 
        row?.customer?.toLowerCase().includes(term)
      );

      const hasMatchingItem = safeData.table_summary.headers.some(
        header => header?.toLowerCase().includes(term)
      );

      if (hasMatchingItem) {
        return {
          headers: safeData.table_summary.headers,
          rows: safeData.table_summary.rows,
          required_quantities: safeData.table_summary.required_quantities || []
        };
      }

      return {
        headers: safeData.table_summary.headers,
        rows: filteredRows,
        required_quantities: safeData.table_summary.required_quantities || []
      };
    };

    setFilteredData({
      available_products: filterAvailableProducts(),
      time_based_orders: filterTimeOrders(),
      item_based_summary: filterItemSummary(),
      customer_based_orders: filterCustomerOrders(),
      table_summary: safeData.table_summary ? filterTableSummary() : { headers: [], rows: [], required_quantities: [] }
    });
  }, [searchTerm, analysisData]);

  // CSV 다운로드 함수
  const downloadCSV = useCallback((dataType) => {
    if (!analysisData) return;

    let csvContent = '\ufeff'; // BOM for UTF-8
    let filename = '';
    
    if (dataType === 'time') {
      filename = `시간순_주문내역_${shopName || '주문'}_${new Date().toISOString().split('T')[0]}.csv`;
      const headers = ['시간', '주문자', '품목', '수량', '비고'];
      csvContent += headers.join(',') + '\n';
      
      if (Array.isArray(analysisData?.time_based_orders)) {
        analysisData.time_based_orders.forEach(order => {
          const row = [
            `"${order?.time || ''}"`,
            `"${order?.customer || ''}"`,
            `"${order?.item || ''}"`,
            `"${order?.quantity || ''}"`,
            `"${order?.note || ''}"`
          ];
          csvContent += row.join(',') + '\n';
        });
      }
    } 
    else if (dataType === 'item') {
      filename = `품목별_주문내역_${shopName || '주문'}_${new Date().toISOString().split('T')[0]}.csv`;
      const headers = ['품목', '총 수량', '주문자 목록'];
      csvContent += headers.join(',') + '\n';
      
      if (Array.isArray(analysisData?.item_based_summary)) {
        analysisData.item_based_summary.forEach(item => {
          const row = [
            `"${item?.item || ''}"`,
            `"${item?.total_quantity || ''}"`,
            `"${item?.customers || ''}"`
          ];
          csvContent += row.join(',') + '\n';
        });
      }
    } 
    else if (dataType === 'customer') {
      filename = `주문자별_주문내역_${shopName || '주문'}_${new Date().toISOString().split('T')[0]}.csv`;
      const headers = ['주문자', '품목', '수량', '비고'];
      csvContent += headers.join(',') + '\n';
      
      if (Array.isArray(analysisData?.customer_based_orders)) {
        analysisData.customer_based_orders.forEach(order => {
          const row = [
            `"${order?.customer || ''}"`,
            `"${order?.item || ''}"`,
            `"${order?.quantity || ''}"`,
            `"${order?.note || ''}"`
          ];
          csvContent += row.join(',') + '\n';
        });
      }
    }
    else if (dataType === 'products') {
      filename = `판매품목_정보_${shopName || '주문'}_${new Date().toISOString().split('T')[0]}.csv`;
      const headers = ['상품명', '카테고리', '가격', '수령일', '마감정보'];
      csvContent += headers.join(',') + '\n';
      
      if (Array.isArray(analysisData?.available_products)) {
        analysisData.available_products.forEach(product => {
          const row = [
            `"${product?.name || ''}"`,
            `"${product?.category || ''}"`,
            `"${product?.price || ''}"`,
            `"${product?.delivery_date || ''}"`,
            `"${product?.deadline || ''}"`
          ];
          csvContent += row.join(',') + '\n';
        });
      }
    }
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [analysisData, shopName]);

  // 다중 시트 엑셀 파일 다운로드 함수
  const downloadExcelWithMultipleSheets = useCallback(() => {
    if (!analysisData) return;

    // 새 워크북 생성
    const workbook = XLSX.utils.book_new();
    
    // 판매 상품 정보 시트 생성
    if (Array.isArray(analysisData?.available_products) && analysisData.available_products.length > 0) {
      const productsData = [['상품명', '카테고리', '가격', '수령일', '마감정보']];
      
      analysisData.available_products.forEach(product => {
        productsData.push([
          product?.name || '',
          product?.category || '',
          product?.price || '',
          product?.delivery_date || '',
          product?.deadline || ''
        ]);
      });
      
      const productsSheet = XLSX.utils.aoa_to_sheet(productsData);
      XLSX.utils.book_append_sheet(workbook, productsSheet, '판매 상품 정보');
    }
    
    // 시간순 주문 내역 시트 생성
    if (Array.isArray(analysisData?.time_based_orders) && analysisData.time_based_orders.length > 0) {
      const timeOrdersData = [['시간', '주문자', '품목', '수량', '비고']];
      
      analysisData.time_based_orders.forEach(order => {
        timeOrdersData.push([
          order?.time || '',
          order?.customer || '',
          order?.item || '',
          order?.quantity || '',
          order?.note || ''
        ]);
      });
      
      const timeOrdersSheet = XLSX.utils.aoa_to_sheet(timeOrdersData);
      XLSX.utils.book_append_sheet(workbook, timeOrdersSheet, '시간순 주문 내역');
    }
    
    // 품목별 주문 요약 시트 생성
    if (Array.isArray(analysisData?.item_based_summary) && analysisData.item_based_summary.length > 0) {
      const itemSummaryData = [['품목', '총 수량', '주문자 목록']];
      
      analysisData.item_based_summary.forEach(item => {
        itemSummaryData.push([
          item?.item || '',
          item?.total_quantity || '',
          item?.customers || ''
        ]);
      });
      
      const itemSummarySheet = XLSX.utils.aoa_to_sheet(itemSummaryData);
      XLSX.utils.book_append_sheet(workbook, itemSummarySheet, '품목별 주문 요약');
    }
    
    // 주문자별 주문 내역 시트 생성
    if (Array.isArray(analysisData?.customer_based_orders) && analysisData.customer_based_orders.length > 0) {
      const customerOrdersData = [['주문자', '품목', '수량', '비고']];
      
      analysisData.customer_based_orders.forEach(order => {
        customerOrdersData.push([
          order?.customer || '',
          order?.item || '',
          order?.quantity || '',
          order?.note || ''
        ]);
      });
      
      const customerOrdersSheet = XLSX.utils.aoa_to_sheet(customerOrdersData);
      XLSX.utils.book_append_sheet(workbook, customerOrdersSheet, '주문자별 주문 내역');
    }
    
    // 주문 요약 테이블 시트 생성
    if (analysisData?.table_summary && Array.isArray(analysisData.table_summary.rows) && 
        analysisData.table_summary.rows.length > 0) {
      // 헤더 행 만들기
      const tableData = [
        ['품목/주문자', ...(analysisData.table_summary.headers || [])]
      ];
      
      // 데이터 행 추가
      analysisData.table_summary.rows.forEach(row => {
        tableData.push(row);
      });
      
      const tableSheet = XLSX.utils.aoa_to_sheet(tableData);
      XLSX.utils.book_append_sheet(workbook, tableSheet, '주문 요약 테이블');
    }
    
    // 주문 패턴 분석 시트 생성
    if (analysisData?.order_pattern_analysis) {
      const analysisData1 = [['매장명', analysisData.shop_name || '']];
      analysisData1.push(['', '']);  // 빈 행 추가
      
      // 피크 시간대
      analysisData1.push(['피크 시간대']);
      if (Array.isArray(analysisData.order_pattern_analysis.peak_hours) && 
          analysisData.order_pattern_analysis.peak_hours.length > 0) {
        analysisData.order_pattern_analysis.peak_hours.forEach(hour => {
          analysisData1.push([hour]);
        });
      } else {
        analysisData1.push(['정보 없음']);
      }
      
      analysisData1.push(['', '']);  // 빈 행 추가
      
      // 인기 품목
      analysisData1.push(['인기 품목']);
      if (Array.isArray(analysisData.order_pattern_analysis.popular_items) && 
          analysisData.order_pattern_analysis.popular_items.length > 0) {
        analysisData.order_pattern_analysis.popular_items.forEach((item, index) => {
          analysisData1.push([`${index + 1}. ${item}`]);
        });
      } else {
        analysisData1.push(['정보 없음']);
      }
      
      analysisData1.push(['', '']);  // 빈 행 추가
      
      // 품절 품목
      analysisData1.push(['품절 품목']);
      if (Array.isArray(analysisData.order_pattern_analysis.sold_out_items) && 
          analysisData.order_pattern_analysis.sold_out_items.length > 0) {
        analysisData.order_pattern_analysis.sold_out_items.forEach(item => {
          analysisData1.push([item]);
        });
      } else {
        analysisData1.push(['정보 없음']);
      }
      
      const analysisSheet = XLSX.utils.aoa_to_sheet(analysisData1);
      XLSX.utils.book_append_sheet(workbook, analysisSheet, '주문 패턴 분석');
    }
    
    // 엑셀 파일로 내보내기
    const filename = `전체_주문내역_${analysisData.shop_name || shopName || '주문'}_${new Date().toISOString().split('T')[0]}.xlsx`;
    XLSX.writeFile(workbook, filename);
    
  }, [analysisData]);

  if (isLoading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner"></div>
        <p>대화 내용을 분석 중입니다. 잠시만 기다려주세요...</p>
      </div>
    );
  }

  if (!analysisData) {
    return null;
  }

  return (
    <div className="result-display">
      <div className="result-header">
        <h2>분석 결과</h2>
        <div className="result-actions">
          <div className="search-box">
            <input
              type="text"
              placeholder="검색어 입력..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="search-input"
            />
            {searchTerm && (
              <button 
                className="clear-search" 
                onClick={() => setSearchTerm('')}
                title="검색어 지우기"
              >
                ✕
              </button>
            )}
          </div>
          <button 
            onClick={downloadExcelWithMultipleSheets} 
            className="download-all-button"
            title="모든 데이터를 Excel 파일로 다운로드"
          >
            전체 데이터 다운로드 (Excel)
          </button>
        </div>
      </div>
      
      <div className="tabs">
        <button
          className={`tab-button ${activeTab === 'products' ? 'active' : ''}`}
          onClick={() => setActiveTab('products')}
        >
          주문품목 ({filteredData?.available_products?.length || 0})
        </button>
        <button
          className={`tab-button ${activeTab === 'time' ? 'active' : ''}`}
          onClick={() => setActiveTab('time')}
        >
          시간순 주문 내역 ({filteredData?.time_based_orders?.length || 0})
        </button>
        <button
          className={`tab-button ${activeTab === 'item' ? 'active' : ''}`}
          onClick={() => setActiveTab('item')}
        >
          품목별 총 주문 갯수 ({filteredData?.item_based_summary?.length || 0})
        </button>
        <button
          className={`tab-button ${activeTab === 'customer' ? 'active' : ''}`}
          onClick={() => setActiveTab('customer')}
        >
          주문자별 주문 내역 ({filteredData?.customer_based_orders?.length || 0})
        </button>
        {analysisData?.table_summary && (
          <button
            className={`tab-button ${activeTab === 'table' ? 'active' : ''}`}
            onClick={() => setActiveTab('table')}
          >
            주문 요약 테이블
          </button>
        )}
        {analysisData?.order_pattern_analysis && (
          <button
            className={`tab-button ${activeTab === 'analysis' ? 'active' : ''}`}
            onClick={() => setActiveTab('analysis')}
          >
            주문 패턴 분석
          </button>
        )}
      </div>
      
      <div className="tab-content">
        {activeTab === 'products' && (
          <div className="products-table">
            <div className="table-actions">
              <button onClick={() => downloadCSV('products')} className="download-button">
                CSV 다운로드
              </button>
            </div>
            
            {(filteredData?.available_products?.length > 0) ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>상품명</th>
                      <th>카테고리</th>
                      <th>가격</th>
                      <th>수령일</th>
                      <th>마감 정보</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.available_products.map((product, index) => (
                      <tr key={`product-${index}`} className={index % 2 === 0 ? 'even-row' : 'odd-row'}>
                        <td>{product?.name || ''}</td>
                        <td>{product?.category || ''}</td>
                        <td>{product?.price || ''}</td>
                        <td>{product?.delivery_date || ''}</td>
                        <td>{product?.deadline || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="no-data-message">
                {searchTerm ? '검색 결과가 없습니다.' : '판매 상품 정보가 없습니다.'}
              </div>
            )}
          </div>
        )}
        
        {activeTab === 'time' && (
          <div className="time-table">
            <div className="table-actions">
              <button onClick={() => downloadCSV('time')} className="download-button">
                CSV 다운로드
              </button>
            </div>
            
            {(filteredData?.time_based_orders?.length > 0) ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>시간</th>
                      <th>주문자</th>
                      <th>품목</th>
                      <th>수량</th>
                      <th>비고</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.time_based_orders.slice(0, 1000).map((order, index) => (
                      <tr key={`time-${index}`} className={index % 2 === 0 ? 'even-row' : 'odd-row'}>
                        <td>{order?.time || ''}</td>
                        <td>{order?.customer || ''}</td>
                        <td>{order?.item || ''}</td>
                        <td>{order?.quantity || ''}</td>
                        <td>{order?.note || ''}</td>
                      </tr>
                    ))}
                    {(filteredData?.time_based_orders?.length > 1000) && (
                      <tr>
                        <td colSpan="5" style={{textAlign: 'center', padding: '10px', color: '#666'}}>
                          최대 1000개 항목만 표시됩니다. (전체 {filteredData.time_based_orders.length}개)
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="no-data-message">
                {searchTerm ? '검색 결과가 없습니다.' : '시간순 주문 내역이 없습니다.'}
              </div>
            )}
          </div>
        )}
        
        {activeTab === 'item' && (
          <div className="item-table">
            <div className="table-actions">
              <button onClick={() => downloadCSV('item')} className="download-button">
                CSV 다운로드
              </button>
            </div>
            
            {(filteredData?.item_based_summary?.length > 0) ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>품목</th>
                      <th>총 주문량</th>
                      <th>주문자 목록</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.item_based_summary.slice(0, 1000).map((item, index) => (
                      <tr key={`item-${index}`} className={index % 2 === 0 ? 'even-row' : 'odd-row'}>
                        <td>{item?.item || ''}</td>
                        <td>{item?.total_quantity || ''}</td>
                        <td>{item?.customers || ''}</td>
                      </tr>
                    ))}
                    {(filteredData?.item_based_summary?.length > 1000) && (
                      <tr>
                        <td colSpan="3" style={{textAlign: 'center', padding: '10px', color: '#666'}}>
                          최대 1000개 항목만 표시됩니다. (전체 {filteredData.item_based_summary.length}개)
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="no-data-message">
                {searchTerm ? '검색 결과가 없습니다.' : '품목별 주문 내역이 없습니다.'}
              </div>
            )}
          </div>
        )}
        
        {activeTab === 'customer' && (
          <div className="customer-table">
            <div className="table-actions">
              <button onClick={() => downloadCSV('customer')} className="download-button">
                CSV 다운로드
              </button>
            </div>
            
            {(filteredData?.customer_based_orders?.length > 0) ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>주문자</th>
                      <th>품목</th>
                      <th>수량</th>
                      <th>비고</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredData.customer_based_orders.slice(0, 1000).map((order, index) => {
                      // 동일한 주문자의 첫번째 항목인지 확인
                      let isFirstOrderForCustomer = true;
                      if (index > 0) {
                        const prevOrder = filteredData.customer_based_orders[index - 1];
                        isFirstOrderForCustomer = prevOrder?.customer !== order?.customer;
                      }
                      
                      // 동일한 주문자의 주문 개수 계산
                      let rowSpan = 1;
                      if (isFirstOrderForCustomer) {
                        // 1000개 제한을 고려하여 rowSpan 계산
                        const totalOrders = filteredData.customer_based_orders.filter(o => 
                          o?.customer === order?.customer
                        );
                        const displayedOrders = totalOrders.filter((_, i) => 
                          filteredData.customer_based_orders.indexOf(totalOrders[0]) + i < 1000
                        );
                        rowSpan = displayedOrders.length || 1;
                      }
                      
                      return (
                        <tr key={`customer-${index}`} className={index % 2 === 0 ? 'even-row' : 'odd-row'}>
                          {isFirstOrderForCustomer && (
                            <td rowSpan={rowSpan} className="customer-cell">
                              {order?.customer || ''}
                            </td>
                          )}
                          <td>{order?.item || ''}</td>
                          <td>{order?.quantity || ''}</td>
                          <td>{isFirstOrderForCustomer ? (order?.note || '') : ''}</td>
                        </tr>
                      );
                    })}
                    {(filteredData?.customer_based_orders?.length > 1000) && (
                      <tr>
                        <td colSpan="4" style={{textAlign: 'center', padding: '10px', color: '#666'}}>
                          최대 1000개 항목만 표시됩니다. (전체 {filteredData.customer_based_orders.length}개)
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="no-data-message">
                {searchTerm ? '검색 결과가 없습니다.' : '주문자별 주문 내역이 없습니다.'}
              </div>
            )}
          </div>
        )}
        
        {activeTab === 'table' && analysisData?.table_summary && (
          <div className="summary-table">
            <div className="table-actions">
              <button onClick={() => {
                // 테이블 형식 CSV 다운로드 로직 구현
                const headers = ['품목/주문자', ...(filteredData?.table_summary?.headers || [])];
                let csvContent = '\ufeff'; // BOM for UTF-8
                const filename = `주문_요약_테이블_${shopName || '주문'}_${new Date().toISOString().split('T')[0]}.csv`;
                
                // 헤더 추가
                csvContent += headers.map(h => `"${h || ''}"`).join(',') + '\n';
                
                // 주문자별 행 추가
                if (Array.isArray(filteredData?.table_summary?.rows)) {
                  filteredData.table_summary.rows.forEach(row => {
                    const rowData = [`"${row[0] || ''}"`];
                    row.slice(1).forEach(cell => {
                      rowData.push(`"${cell || ''}"`);
                    });
                    csvContent += rowData.join(',') + '\n';
                  });
                }
                
                // 다운로드
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.setAttribute('href', url);
                link.setAttribute('download', filename);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }} className="download-button">
                CSV 다운로드
              </button>
            </div>
            
            {(filteredData?.table_summary?.headers?.length > 0 || (filteredData?.table_summary?.rows?.length > 0)) ? (
              <div className="table-container">
                <table className="matrix-table">
                  <thead>
                    <tr>
                      <th>품목/주문자</th>
                      {filteredData.table_summary.headers.map((header, index) => (
                        <th key={`header-${index}`}>{header || ''}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.isArray(filteredData?.table_summary?.rows) && filteredData.table_summary.rows.map((row, rowIndex) => (
                      <tr key={`row-${rowIndex}`} className={rowIndex % 2 === 0 ? 'even-row' : 'odd-row'}>
                        <td className="customer-cell">{row[0] || ''}</td>
                        {row.slice(1).map((cell, cellIndex) => (
                          <td key={`cell-${rowIndex}-${cellIndex}`}>
                            {cell || ''}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {/* 필요시 필요수량 행 추가 - 현재는 표시하지 않음 */}
                    {/*
                    <tr className="required-quantities-row">
                      <td><strong>필요수량</strong></td>
                      {Array.isArray(filteredData?.table_summary?.required_quantities) && 
                       filteredData.table_summary.required_quantities.map((qty, index) => (
                        <td key={`required-${index}`}><strong>{qty || ''}</strong></td>
                      ))}
                    </tr>
                    */}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="no-data-message">
                {searchTerm ? '검색 결과가 없습니다.' : '테이블 형식 요약 데이터가 없습니다.'}
              </div>
            )}
          </div>
        )}
        
        {activeTab === 'analysis' && filteredData?.order_pattern_analysis && (
          <div className="order-pattern-analysis">
            <div className="shop-name">
              {filteredData.shop_name && (
                <div className="shop-info">
                  <h3>매장 정보</h3>
                  <p><strong>매장명:</strong> {filteredData.shop_name}</p>
                </div>
              )}
            </div>
            
            <div className="analysis-grid">
              <div className="analysis-card">
                <h3>피크 시간대</h3>
                {filteredData.order_pattern_analysis.peak_hours && 
                 filteredData.order_pattern_analysis.peak_hours.length > 0 ? (
                  <ul className="analysis-list">
                    {filteredData.order_pattern_analysis.peak_hours.map((hour, index) => (
                      <li key={`peak-${index}`} className="analysis-item">
                        <span className="analysis-value">{hour}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">피크 시간대 정보가 없습니다.</p>
                )}
              </div>
              
              <div className="analysis-card">
                <h3>인기 품목</h3>
                {filteredData.order_pattern_analysis.popular_items && 
                 filteredData.order_pattern_analysis.popular_items.length > 0 ? (
                  <ul className="analysis-list">
                    {filteredData.order_pattern_analysis.popular_items.map((item, index) => (
                      <li key={`popular-${index}`} className="analysis-item">
                        <span className="analysis-value">{index + 1}. {item}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">인기 품목 정보가 없습니다.</p>
                )}
              </div>
              
              <div className="analysis-card">
                <h3>품절 품목</h3>
                {filteredData.order_pattern_analysis.sold_out_items && 
                 filteredData.order_pattern_analysis.sold_out_items.length > 0 ? (
                  <ul className="analysis-list">
                    {filteredData.order_pattern_analysis.sold_out_items.map((item, index) => (
                      <li key={`soldout-${index}`} className="analysis-item">
                        <span className="analysis-value">{item}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">품절 품목 정보가 없습니다.</p>
                )}
              </div>
            </div>
            
            <div className="analysis-footer">
              <button onClick={() => {
                // 분석 데이터 CSV 다운로드
                let csvContent = '\ufeff'; // BOM for UTF-8
                const filename = `주문_분석_요약_${filteredData.shop_name || '주문'}_${new Date().toISOString().split('T')[0]}.csv`;
                
                csvContent += "매장명,\n";
                csvContent += `"${filteredData.shop_name || ''}",\n\n`;
                
                // 피크 시간대
                csvContent += "피크 시간대,\n";
                if (filteredData.order_pattern_analysis.peak_hours && 
                    filteredData.order_pattern_analysis.peak_hours.length > 0) {
                  filteredData.order_pattern_analysis.peak_hours.forEach(hour => {
                    csvContent += `"${hour}",\n`;
                  });
                } else {
                  csvContent += "정보 없음,\n";
                }
                csvContent += '\n';
                
                // 인기 품목
                csvContent += "인기 품목,\n";
                if (filteredData.order_pattern_analysis.popular_items && 
                    filteredData.order_pattern_analysis.popular_items.length > 0) {
                  filteredData.order_pattern_analysis.popular_items.forEach((item, index) => {
                    csvContent += `"${index + 1}. ${item}",\n`;
                  });
                } else {
                  csvContent += "정보 없음,\n";
                }
                csvContent += '\n';
                
                // 품절 품목
                csvContent += "품절 품목,\n";
                if (filteredData.order_pattern_analysis.sold_out_items && 
                    filteredData.order_pattern_analysis.sold_out_items.length > 0) {
                  filteredData.order_pattern_analysis.sold_out_items.forEach(item => {
                    csvContent += `"${item}",\n`;
                  });
                } else {
                  csvContent += "정보 없음,\n";
                }
                
                // 다운로드
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.setAttribute('href', url);
                link.setAttribute('download', filename);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
              }} className="download-button">
                CSV 다운로드
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ResultDisplay;
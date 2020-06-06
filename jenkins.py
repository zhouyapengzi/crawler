import json
import csv
import logging
import datetime
import os

import requests


def get_build(jenkins_url, output_directory):
    logging.info('Processing build batch for' + jenkins_url + '...')
    response = json.loads(requests.get(jenkins_url).text)
    builds = []
    output_file = os.path.join(output_directory,'BuildSummary.csv')
    with open(output_file,'w') as wf:
        wf_writer = csv.writer(wf)
        wf_writer.writerow(["JobName","ID","URL","TimeStamp","Result","Test_TotalCount",'Test_SkipCount','test_FailCount'])
        for build in response["builds"]:
            build_url = build["url"]
            builds.append(build_url)
            build_time_stamp = datetime.datetime.utcfromtimestamp(build['timestamp'] / 1000).isoformat()

            build_total_count = '0'
            build_skip_count = '0'
            build_fail_count = '0'
            for action in build['actions']:
                if 'totalCount' in action.keys():
                    build_total_count = action['totalCount']
                    build_skip_count = action['skipCount']
                    build_fail_count = action['failCount']
            wf_writer.writerow([build['fullDisplayName'],str(build['number']),str(build_url),
                               build_time_stamp,str(build['result']),str(build_total_count),
                               str(build_skip_count),str(build_fail_count)])
    wf.close()
    print('total builds: %s' % len(builds))
    return builds


def get_test_report(builds,output_directory):
    for build_url in builds:
        build_no = build_url[build_url[:build_url.rfind('/')].rfind('/') + 1: build_url.rfind('/')]
        build_url += 'testReport/api/json?tree=suites[cases[className,name,duration,status,skipped]]'
        # build_url +='testReport/api/json?depth=2'
        logging.info('parsing build:' + build_url)
        if not requests.get(build_url).ok:
            logging.info("build has no test report, skip:" + build_url)
            continue

        test_response = json.loads(requests.get(build_url).text)
        output_detail_file = open(os.path.join(output_directory,build_no+'_detail_bk.json'), 'w')
        output_detail_file.write(json.dumps(test_response, indent=4, sort_keys=True))
        output_detail_file.close()

        out = os.path.join(output_directory,build_no+'.csv')
        with open(out,'w') as of:
            file_writer = csv.writer(of)
            file_writer.writerow(['ClassName','Duration'])
            cases = test_response['suites']
            for case in cases:
                class_duration = 0
                class_name = ""
                for tests in case['cases']:
                    class_duration += tests['duration']
                    class_name = tests['className']
                file_writer.writerow([class_name, str(class_duration)])
        of.close()


def create_output_directory(project):
    # create output folder for the project
    if not os.path.isdir('output'):
        os.mkdir('output')
    output_path = os.path.join('output',project)
    if not os.path.isdir(output_path):
        os.mkdir(output_path)
    return output_path


def main():
    url = "https://builds.apache.org/view/H-L/view/Hive/"
    job_info = "Hive-linux-ARM-trunk"
    output_directory = create_output_directory('hive')
    if not url.endswith('/'):
        url += '/'
    #jenkins_url = url + 'job/' + job_info + '/api/json??tree=allBuilds[number,url]'
    jenkins_url = url + 'job/' + job_info + '/api/json?depth=2'
    builds = get_build(jenkins_url,output_directory)
    get_test_report(builds, output_directory)


if __name__ == '__main__':
    main()
